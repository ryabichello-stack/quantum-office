"""HTTP MCP gateway for Hermes / Cursor / Grok (multi-tenant)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_access_token
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.models.user import User
from app.services.mcp_gateway import (
    PROTOCOL_VERSION,
    SERVER_NAME,
    build_hermes_profile,
    call_mcp_tool,
    find_tenant_by_mcp_key,
    mcp_content_result,
    mcp_tools_catalog,
    unwrap_for_http,
)
from app.services.hermes_nous.mcp_scope import filter_tools_catalog, tool_allowed
from app.services.hermes_nous.run_tokens import verify_run_token

router = APIRouter(prefix="/mcp", tags=["mcp"])
hermes_router = APIRouter(prefix="/hermes", tags=["hermes"])
_bearer = HTTPBearer(auto_error=False)
GATEWAY_VERSION = "0.1.0"


class ToolCallBody(BaseModel):
    name: str = Field(..., min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class McpAuthContext:
    """MCP auth: tenant + optional Nous run-token grants (fail-closed tools/list)."""

    tenant: TenantContext
    auth_via: str = "unknown"
    run_token_tool_ids: list[str] | None = None
    run_id: str | None = None

    @property
    def tenant_slug(self) -> str:
        return self.tenant.tenant_slug


def get_mcp_tenant_context(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    x_api_key: Optional[str] = Header(default=None, alias="X-Api-Key"),
    x_delno_mcp_key: Optional[str] = Header(default=None, alias="X-Delno-Mcp-Key"),
    x_delno_run_token: Optional[str] = Header(default=None, alias="X-Delno-Run-Token"),
) -> McpAuthContext:
    """Accept JWT, scoped run token (Nous), or legacy per-tenant mcp_api_key."""
    raw = ""
    if x_delno_run_token:
        raw = x_delno_run_token.strip()
    elif credentials and credentials.scheme.lower() == "bearer":
        raw = credentials.credentials.strip()
    elif x_delno_mcp_key:
        raw = x_delno_mcp_key.strip()
    elif x_api_key:
        raw = x_api_key.strip()

    if not raw:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Nous scoped run token (preferred for Hermes runtimes)
    run_entry = verify_run_token(db, raw)
    if run_entry:
        tenant = run_entry["tenant"]
        actor = run_entry.get("actor_user_id")
        return McpAuthContext(
            tenant=TenantContext(
                tenant_id=tenant.id,
                tenant_slug=tenant.slug,
                user_id=UUID(str(actor)) if actor else None,
                role=str(run_entry.get("role") or "tenant_owner"),
            ),
            auth_via="run_token",
            run_token_tool_ids=list(run_entry.get("tool_ids") or []),
            run_id=str(run_entry.get("run_id") or ""),
        )

    # Try JWT
    try:
        payload = decode_access_token(raw)
        user_id = payload.get("sub")
        if user_id:
            user = db.query(User).filter(User.id == UUID(str(user_id))).one_or_none()
            if user:
                tenant = (
                    db.query(Tenant)
                    .filter(Tenant.id == user.tenant_id, Tenant.is_active.is_(True))
                    .one_or_none()
                )
                if not tenant:
                    raise HTTPException(status_code=404, detail="Tenant not found")
                return McpAuthContext(
                    tenant=TenantContext(
                        tenant_id=tenant.id,
                        tenant_slug=tenant.slug,
                        user_id=user.id,
                        role=user.role,
                    ),
                    auth_via="jwt",
                )
    except ValueError:
        pass

    tenant = find_tenant_by_mcp_key(db, raw)
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid token or mcp key")
    return McpAuthContext(
        tenant=TenantContext(
            tenant_id=tenant.id,
            tenant_slug=tenant.slug,
            user_id=None,
            role="tenant_owner",
        ),
        auth_via="mcp_api_key",
    )


def _scoped_catalog(ctx: McpAuthContext) -> list[dict[str, Any]]:
    catalog = mcp_tools_catalog()
    if ctx.auth_via == "run_token":
        return filter_tools_catalog(catalog, ctx.run_token_tool_ids)
    return catalog


@router.get("/health")
def mcp_health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": SERVER_NAME,
        "version": GATEWAY_VERSION,
        "tools": len(mcp_tools_catalog()),
        "protocol": PROTOCOL_VERSION,
        "endpoints": [
            "/v1/mcp/health",
            "/v1/mcp/tools",
            "/v1/mcp/tools/call",
            "/v1/mcp",
            "/v1/mcp/openapi-lite",
            "/v1/hermes/profile",
        ],
    }


@router.get("/tools")
def mcp_list_tools(ctx: McpAuthContext = Depends(get_mcp_tenant_context)) -> dict[str, Any]:
    tools = _scoped_catalog(ctx)
    return {
        "ok": True,
        "tenant_slug": ctx.tenant_slug,
        "auth_via": ctx.auth_via,
        "count": len(tools),
        "tools": tools,
    }


@router.get("/openapi-lite")
def mcp_openapi_lite(ctx: McpAuthContext = Depends(get_mcp_tenant_context)) -> dict[str, Any]:
    tools = _scoped_catalog(ctx)
    return {
        "ok": True,
        "service": SERVER_NAME,
        "tenant_slug": ctx.tenant_slug,
        "auth": "Authorization: Bearer <jwt|run_token|mcp_api_key> or X-Delno-Run-Token / X-Delno-Mcp-Key",
        "call": "POST /v1/mcp/tools/call",
        "tools": [
            {"name": t["name"], "description": t.get("description"), "inputSchema": t.get("inputSchema")}
            for t in tools
        ],
    }


@router.post("/tools/call")
def mcp_tools_call(
    body: ToolCallBody,
    db: Session = Depends(get_db),
    ctx: McpAuthContext = Depends(get_mcp_tenant_context),
) -> dict[str, Any]:
    if ctx.auth_via == "run_token" and not tool_allowed(body.name, ctx.run_token_tool_ids):
        raise HTTPException(status_code=403, detail={"error": "tool_not_granted", "tool": body.name})
    payload = call_mcp_tool(db, ctx.tenant, body.name, body.arguments or {})
    return unwrap_for_http(body.name, payload)


@router.post("")
async def mcp_jsonrpc(
    request: Request,
    db: Session = Depends(get_db),
    ctx: McpAuthContext = Depends(get_mcp_tenant_context),
) -> JSONResponse:
    try:
        msg = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid json: {exc}") from exc

    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        result: Any = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": GATEWAY_VERSION},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": _scoped_catalog(ctx)}
    elif method == "tools/call":
        name = str((params.get("name") if isinstance(params, dict) else "") or "")
        arguments = params.get("arguments") if isinstance(params, dict) else {}
        if not isinstance(arguments, dict):
            arguments = {}
        if ctx.auth_via == "run_token" and not tool_allowed(name, ctx.run_token_tool_ids):
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32003, "message": f"tool_not_granted: {name}"},
                }
            )
        payload = call_mcp_tool(db, ctx.tenant, name, arguments)
        is_error = not bool(payload.get("ok", True)) or bool(payload.get("needs_confirmation"))
        result = mcp_content_result(payload, is_error=is_error)
    elif method == "notifications/initialized":
        return JSONResponse(content={})
    else:
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        )

    return JSONResponse(content={"jsonrpc": "2.0", "id": msg_id, "result": result})


@hermes_router.get("/profile")
def hermes_profile(
    db: Session = Depends(get_db),
    ctx: McpAuthContext = Depends(get_mcp_tenant_context),
) -> dict[str, Any]:
    """Hermes multi-user profile: toolset + MCP endpoints.

    With run_token auth: never return long-lived mcp_api_key; catalog is scoped.
    """
    include_key = ctx.auth_via != "run_token"
    profile = build_hermes_profile(db, ctx.tenant, include_mcp_key=include_key)
    if ctx.auth_via == "run_token":
        profile["toolset"] = {
            "total": len(_scoped_catalog(ctx)),
            "tools": _scoped_catalog(ctx),
        }
        profile["auth_via"] = "run_token"
        profile["run_id"] = ctx.run_id
        profile.pop("mcp_api_key", None)
    return profile
