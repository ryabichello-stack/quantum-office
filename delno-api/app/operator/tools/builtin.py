from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.adapters.knowledge import KnowledgeAdapter
from app.core.principals import principal_for_operator
from app.core.tenant import TenantContext
from app.models.feature_flag import FeatureFlag
from app.models.tenant import Tenant
from app.operator.tools.registry import ToolResult
from app.services.audit import write_audit
from app.services.events import emit_event
from app.services.knowledge_documents import upsert_tenant_knowledge_document
from app.services.leads import create_lead_record
from app.services.party_enrichment import lookup_party_by_inn
from app.services.tenant_settings_ingest import sync_tenant_settings_for_ctx


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


class GetTenantSummaryTool:
    name = "get_tenant_summary"
    description = "Read tenant settings, legal profile and feature flags (read-only)."
    critical_write = False
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
        settings = tenant.settings if isinstance(tenant.settings, dict) else {}
        flags = (
            db.query(FeatureFlag)
            .filter(FeatureFlag.tenant_id == ctx.tenant_id)
            .order_by(FeatureFlag.flag_key)
            .all()
        )
        write_audit(
            db,
            ctx,
            action="tool.get_tenant_summary",
            resource=f"tenant:{tenant.id}",
            new_value={"flags": len(flags)},
        )
        return ToolResult(
            ok=True,
            data={
                "tenant_name": tenant.name,
                "tenant_slug": tenant.slug,
                "settings": settings,
                "feature_flags": {f.flag_key: f.enabled for f in flags},
            },
            message="Tenant summary loaded",
        )


class UpdateTenantSettingsTool:
    name = "update_tenant_settings"
    description = "Merge patch into tenant.settings (greeting, assistant_name, business note)."
    critical_write = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "patch": {"type": "object", "description": "Partial settings dict to merge"},
        },
        "required": ["patch"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        patch = params.get("patch")
        if not isinstance(patch, dict) or not patch:
            return ToolResult(ok=False, message="patch object is required")

        tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
        old_settings = dict(tenant.settings or {})
        merged = {**old_settings, **patch}
        tenant.settings = merged

        sync = sync_tenant_settings_for_ctx(db, ctx, source="operator.update_settings")
        write_audit(
            db,
            ctx,
            action="tool.update_tenant_settings",
            resource=f"tenant:{tenant.id}",
            old_value={"settings": old_settings},
            new_value={"settings": merged, "knowledge_sync": sync},
        )
        emit_event(
            db,
            tenant_id=ctx.tenant_id,
            event_type="tenant.settings.updated",
            category="operational",
            source="operator.update_settings",
            payload={"keys": list(patch.keys())},
        )
        db.commit()
        return ToolResult(
            ok=True,
            data={"settings": merged, "knowledge_sync": sync},
            message="Settings updated",
        )


class UploadKnowledgeSnippetTool:
    name = "upload_knowledge_snippet"
    description = "Upsert a KB text document for the tenant."
    critical_write = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "body": {"type": "string"},
            "visibility": {"type": "string", "enum": ["public", "company"]},
        },
        "required": ["title", "body"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        title = str(params.get("title") or "").strip()
        body = str(params.get("body") or "").strip()
        visibility = str(params.get("visibility") or "public")
        if len(title) < 2 or len(body) < 10:
            return ToolResult(ok=False, message="title and body (min 10 chars) are required")

        tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
        result = upsert_tenant_knowledge_document(
            db,
            tenant,
            title=title[:255],
            body=body[:50000],
            visibility=visibility if visibility in ("public", "company") else "public",
            source="operator.knowledge_snippet",
        )
        if not result.get("ok"):
            write_audit(
                db,
                ctx,
                action="tool.upload_knowledge_snippet",
                resource="knowledge",
                new_value={"title": title, "ok": False},
                result="error",
            )
            return ToolResult(ok=False, data=result, message=str(result.get("detail") or "knowledge_failed"))

        write_audit(
            db,
            ctx,
            action="tool.upload_knowledge_snippet",
            resource="knowledge",
            new_value={"title": title, "document_id": result.get("document_id")},
        )
        db.commit()
        return ToolResult(
            ok=True,
            data=result,
            message=f"Knowledge document «{title}» saved",
        )


class SetFeatureFlagTool:
    name = "set_feature_flag"
    description = "Enable or disable a tenant feature flag."
    critical_write = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "flag_key": {"type": "string"},
            "enabled": {"type": "boolean"},
        },
        "required": ["flag_key", "enabled"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        flag_key = str(params.get("flag_key") or "").strip()
        enabled = bool(params.get("enabled"))
        if not flag_key:
            return ToolResult(ok=False, message="flag_key is required")

        flag = (
            db.query(FeatureFlag)
            .filter(FeatureFlag.tenant_id == ctx.tenant_id, FeatureFlag.flag_key == flag_key)
            .one_or_none()
        )
        if not flag:
            return ToolResult(ok=False, message=f"Feature flag not found: {flag_key}")

        old = flag.enabled
        flag.enabled = enabled
        emit_event(
            db,
            tenant_id=ctx.tenant_id,
            event_type="feature.flag.updated",
            category="operational",
            source="operator.set_feature_flag",
            payload={"flag_key": flag_key, "enabled": enabled},
        )
        write_audit(
            db,
            ctx,
            action="tool.set_feature_flag",
            resource=f"feature_flag:{flag_key}",
            old_value={"enabled": old},
            new_value={"enabled": enabled},
        )
        db.commit()
        return ToolResult(
            ok=True,
            data={"flag_key": flag_key, "enabled": enabled},
            message=f"Flag {flag_key} → {'on' if enabled else 'off'}",
        )
