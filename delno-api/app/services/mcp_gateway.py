"""Multi-tenant MCP façade over the operator ToolRegistry + connectors.

Tools-first: works with JWT or per-tenant mcp_api_key; no OpenAI required.
Compatible shape with quantum-office HTTP gateway (tools / tools/call / mcp).
"""

from __future__ import annotations

import json
import secrets
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.tenant import TenantContext
from app.models.feature_flag import FeatureFlag
from app.models.tenant import Tenant
from app.operator.tools.registry import PendingConfirmation, ToolResult, registry
from app.services.audit import write_audit
from app.services.connectors import list_tenant_connectors
from app.services.events import emit_event

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "delno-mcp"


def _settings_dict(tenant: Tenant) -> dict[str, Any]:
    return dict(tenant.settings) if isinstance(tenant.settings, dict) else {}


def ensure_mcp_api_key(db: Session, tenant: Tenant) -> str:
    """Mint a per-tenant MCP key if missing (tools-first dogfood)."""
    settings = _settings_dict(tenant)
    existing = str(settings.get("mcp_api_key") or "").strip()
    if existing:
        return existing
    key = f"dmcp_{secrets.token_urlsafe(24)}"
    settings["mcp_api_key"] = key
    tenant.settings = settings
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return key


def find_tenant_by_mcp_key(db: Session, key: str) -> Tenant | None:
    key = (key or "").strip()
    if not key:
        return None
    # JSON containment works on Postgres JSONB; scan fallback for unit tests.
    try:
        tenant = (
            db.query(Tenant)
            .filter(Tenant.is_active.is_(True))
            .filter(Tenant.settings.contains({"mcp_api_key": key}))
            .one_or_none()
        )
        if tenant:
            return tenant
    except Exception:
        pass
    for tenant in db.query(Tenant).filter(Tenant.is_active.is_(True)).all():
        settings = _settings_dict(tenant)
        if str(settings.get("mcp_api_key") or "") == key:
            return tenant
    return None


def mcp_tools_catalog() -> list[dict[str, Any]]:
    """MCP tools/list shape from registry (no tenant filter — ACL on call)."""
    tools: list[dict[str, Any]] = []
    for item in registry.list_catalog():
        tools.append(
            {
                "name": item["name"],
                "description": item["description"],
                "inputSchema": item.get("parameters_schema")
                or {"type": "object", "properties": {}},
            }
        )
    # Meta tools for Hermes / agents
    tools.extend(
        [
            {
                "name": "office.health",
                "description": "DELNO MCP gateway health + tool counts for this deployment.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "office.connectors",
                "description": "List tenant office connectors (mail/calendar/files/conference) and stub status.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "hermes.profile",
                "description": "Return Hermes profile manifest for the authenticated tenant (toolset + MCP URLs).",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]
    )
    return tools


def _tool_result_payload(result: ToolResult | PendingConfirmation | dict[str, Any]) -> dict[str, Any]:
    if isinstance(result, PendingConfirmation):
        return {
            "ok": False,
            "needs_confirmation": True,
            "confirmation_id": result.confirmation_id,
            "tool_name": result.tool_name,
            "summary": result.summary,
            "payload": result.payload,
        }
    if isinstance(result, ToolResult):
        out = {"ok": result.ok, "message": result.message, **(result.data or {})}
        return out
    if isinstance(result, dict):
        return result
    return {"ok": False, "error": "unknown_result"}


def call_mcp_tool(db: Session, ctx: TenantContext, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    args = arguments or {}
    name = (name or "").strip()

    if name == "office.health":
        return {
            "ok": True,
            "service": SERVER_NAME,
            "tenant_slug": ctx.tenant_slug,
            "tools": len(mcp_tools_catalog()),
            "registry_tools": len(registry.list_catalog()),
        }

    if name == "office.connectors":
        return list_tenant_connectors(db, ctx)

    if name == "hermes.profile":
        return build_hermes_profile(db, ctx, include_mcp_key=False)

    tool = registry.get(name)
    if not tool:
        return {"ok": False, "error": "unknown_tool", "tool": name}

    result = registry.run(db, ctx, name, **args)
    payload = _tool_result_payload(result)
    write_audit(
        db,
        ctx,
        action="mcp.tools.call",
        resource=f"tool:{name}",
        new_value={"ok": bool(payload.get("ok")), "needs_confirmation": bool(payload.get("needs_confirmation"))},
    )
    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="mcp.tool_called",
        category="operational",
        source="mcp.gateway",
        payload={"tool": name, "ok": bool(payload.get("ok"))},
    )
    db.commit()
    return payload


def public_api_base() -> str:
    settings = get_settings()
    base = (settings.api_public_base_url or "").strip().rstrip("/")
    if base:
        return base
    return "http://127.0.0.1:18020"


def build_hermes_profile(db: Session, ctx: TenantContext, *, include_mcp_key: bool = True) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    mcp_key = ensure_mcp_api_key(db, tenant) if include_mcp_key else str(_settings_dict(tenant).get("mcp_api_key") or "")
    flags = (
        db.query(FeatureFlag)
        .filter(FeatureFlag.tenant_id == ctx.tenant_id)
        .order_by(FeatureFlag.flag_key)
        .all()
    )
    connectors = list_tenant_connectors(db, ctx)
    base = public_api_base()
    mcp_base = f"{base}/v1/mcp"
    tools = mcp_tools_catalog()
    profile = {
        "ok": True,
        "profile_id": tenant.slug,
        "profile_kind": "hermes_tenant",
        "tenant_id": str(tenant.id),
        "tenant_slug": tenant.slug,
        "tenant_name": tenant.name,
        "display_name": f"DELNO · {tenant.name}",
        "toolset": {
            "total": len(tools),
            "tools": tools,
        },
        "connectors": connectors.get("items", []),
        "feature_flags": [{"flag_key": f.flag_key, "enabled": f.enabled} for f in flags],
        "mcp": {
            "transport": "http",
            "protocol_version": PROTOCOL_VERSION,
            "server": SERVER_NAME,
            "base_url": mcp_base,
            "auth": {
                "type": "bearer_or_header",
                "headers": ["Authorization: Bearer <mcp_api_key|jwt>", "X-Delno-Mcp-Key: <mcp_api_key>"],
            },
            "endpoints": {
                "health": f"{mcp_base}/health",
                "tools": f"{mcp_base}/tools",
                "tools_call": f"{mcp_base}/tools/call",
                "jsonrpc": f"{mcp_base}",
                "openapi_lite": f"{mcp_base}/openapi-lite",
            },
        },
        "policy": {
            "creds": "tools_first",
            "note": "Connectors/tools work in stub mode until OpenAI/Telegram/DaData/BASE_URL keys are set.",
        },
    }
    if include_mcp_key and mcp_key:
        profile["mcp_api_key"] = mcp_key
    return profile


def unwrap_for_http(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": bool(payload.get("ok", True)) and not payload.get("needs_confirmation"),
        "tool": tool_name,
        "result": payload,
    }


def mcp_content_result(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": text}], "isError": is_error}
