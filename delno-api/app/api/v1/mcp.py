"""HTTP MCP gateway for Hermes / Cursor / Grok (multi-tenant)."""

from __future__ import annotations

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

router = APIRouter(prefix="/mcp", tags=["mcp"])
hermes_router = APIRouter(prefix="/hermes", tags=["hermes"])
_bearer = HTTPBearer(auto_error=False)
GATEWAY_VERSION = "0.1.0"


class ToolCallBody(BaseModel):
    name: str = Field(..., min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


def get_mcp_tenant_context(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    x_api_key: Optional[str] = Header(default=None, alias="X-Api-Key"),
    x_delno_mcp_key: Optional[str] = Header(default=None, alias="X-Delno-Mcp-Key"),
) -> TenantContext:
    """Accept JWT (user) or per-tenant mcp_api_key."""
    raw = ""
    if credentials and credentials.scheme.lower() == "bearer":
        raw = credentials.credentials.strip()
    elif x_delno_mcp_key:
        raw = x_delno_mcp_key.strip()
    elif x_api_key:
        raw = x_api_key.strip()

    if not raw:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Try JWT first
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
                return TenantContext(
                    tenant_id=tenant.id,
                    tenant_slug=tenant.slug,
                    user_id=user.id,
                    role=user.role,
                )
    except ValueError:
        pass

    tenant = find_tenant_by_mcp_key(db, raw)
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid token or mcp key")
    return TenantContext(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        user_id=None,
        role="tenant_owner",
    )


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
def mcp_list_tools(ctx: TenantContext = Depends(get_mcp_tenant_context)) -> dict[str, Any]:
    tools = mcp_tools_catalog()
    return {"ok": True, "tenant_slug": ctx.tenant_slug, "count": len(tools), "tools": tools}


@router.get("/openapi-lite")
def mcp_openapi_lite(ctx: TenantContext = Depends(get_mcp_tenant_context)) -> dict[str, Any]:
    tools = mcp_tools_catalog()
    return {
        "ok": True,
        "service": SERVER_NAME,
        "tenant_slug": ctx.tenant_slug,
        "auth": "Authorization: Bearer <jwt|mcp_api_key> or X-Delno-Mcp-Key",
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
    ctx: TenantContext = Depends(get_mcp_tenant_context),
) -> dict[str, Any]:
    payload = call_mcp_tool(db, ctx, body.name, body.arguments or {})
    return unwrap_for_http(body.name, payload)


@router.post("")
async def mcp_jsonrpc(
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_mcp_tenant_context),
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
        result = {"tools": mcp_tools_catalog()}
    elif method == "tools/call":
        name = str((params.get("name") if isinstance(params, dict) else "") or "")
        arguments = params.get("arguments") if isinstance(params, dict) else {}
        if not isinstance(arguments, dict):
            arguments = {}
        payload = call_mcp_tool(db, ctx, name, arguments)
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
    ctx: TenantContext = Depends(get_mcp_tenant_context),
) -> dict[str, Any]:
    """Hermes multi-user profile: toolset + MCP endpoints + tenant mcp_api_key."""
    return build_hermes_profile(db, ctx, include_mcp_key=True)
