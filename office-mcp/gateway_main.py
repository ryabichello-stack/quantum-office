"""HTTP access point for Grok / remote agents (Bearer API key).

Endpoints:
  GET  /health
  GET  /tools
  GET  /openapi-lite
  POST /tools/call   {"name": "...", "arguments": {...}}
  POST /mcp          JSON-RPC: initialize | tools/list | tools/call | ping
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# Ensure package imports work when launched as script
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quantum_office_mcp import __version__
from quantum_office_mcp.handlers import call_tool
from quantum_office_mcp.tools import TOOLS

API_KEY = (os.getenv("OFFICE_MCP_API_KEY") or "").strip()
HOST = os.getenv("OFFICE_MCP_GATEWAY_HOST", "127.0.0.1")
PORT = int(os.getenv("OFFICE_MCP_GATEWAY_PORT", "8021"))

app = FastAPI(
    title="Quantum Office MCP Gateway",
    version=__version__,
    description="Remote tool gateway for Grok / Cursor (Bearer OFFICE_MCP_API_KEY)",
)


@app.on_event("startup")
def _startup() -> None:
    global API_KEY
    ensure_api_key_file(ROOT / ".env")
    load_dotenv(ROOT / ".env", override=True)
    API_KEY = (os.getenv("OFFICE_MCP_API_KEY") or "").strip()


def _extract_key(
    authorization: Optional[str],
    x_api_key: Optional[str],
    x_office_mcp_key: Optional[str],
) -> str:
    if x_office_mcp_key:
        return x_office_mcp_key.strip()
    if x_api_key:
        return x_api_key.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def _require_key(
    authorization: Optional[str] = None,
    x_api_key: Optional[str] = None,
    x_office_mcp_key: Optional[str] = None,
) -> None:
    if not API_KEY:
        raise HTTPException(503, "OFFICE_MCP_API_KEY not configured")
    got = _extract_key(authorization, x_api_key, x_office_mcp_key)
    if not got or not hmac.compare_digest(got, API_KEY):
        raise HTTPException(401, "Unauthorized")


class ToolCallBody(BaseModel):
    name: str = Field(..., min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


def _unwrap_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize MCP tool result → JSON object for HTTP clients."""
    is_error = bool(result.get("isError"))
    content = result.get("content") or []
    text = ""
    if content and isinstance(content[0], dict):
        text = str(content[0].get("text") or "")
    payload: Any
    try:
        payload = json.loads(text) if text else {"ok": not is_error}
    except json.JSONDecodeError:
        payload = {"ok": not is_error, "text": text}
    if isinstance(payload, dict):
        out = dict(payload)
        if is_error:
            out.setdefault("ok", False)
            out["mcp_is_error"] = True
        else:
            out.setdefault("ok", True)
        return out
    return {"ok": not is_error, "data": payload, "mcp_is_error": is_error}


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "quantum-office-mcp-gateway",
        "version": __version__,
        "tools": len(TOOLS),
        "auth_configured": bool(API_KEY),
        "endpoints": ["/health", "/tools", "/tools/call", "/mcp", "/openapi-lite"],
    }


@app.get("/tools")
def list_tools(
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="X-Api-Key"),
    x_office_mcp_key: Optional[str] = Header(default=None, alias="X-Office-Mcp-Key"),
) -> dict[str, Any]:
    _require_key(authorization, x_api_key, x_office_mcp_key)
    return {"ok": True, "count": len(TOOLS), "tools": TOOLS}


@app.get("/openapi-lite")
def openapi_lite(
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="X-Api-Key"),
    x_office_mcp_key: Optional[str] = Header(default=None, alias="X-Office-Mcp-Key"),
) -> dict[str, Any]:
    """Compact tool catalog for LLM agents (name + description + schema)."""
    _require_key(authorization, x_api_key, x_office_mcp_key)
    return {
        "ok": True,
        "service": "quantum-office",
        "auth": "Authorization: Bearer <OFFICE_MCP_API_KEY>",
        "call": "POST /tools/call",
        "tools": [
            {
                "name": t["name"],
                "description": t.get("description"),
                "inputSchema": t.get("inputSchema"),
            }
            for t in TOOLS
        ],
    }


@app.post("/tools/call")
def tools_call(
    body: ToolCallBody,
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="X-Api-Key"),
    x_office_mcp_key: Optional[str] = Header(default=None, alias="X-Office-Mcp-Key"),
) -> dict[str, Any]:
    _require_key(authorization, x_api_key, x_office_mcp_key)
    result = call_tool(body.name, body.arguments or {})
    payload = _unwrap_tool_result(result)
    return {
        "ok": bool(payload.get("ok", True)) and not payload.get("mcp_is_error"),
        "tool": body.name,
        "result": payload,
    }


@app.post("/mcp")
async def mcp_jsonrpc(request: Request) -> JSONResponse:
    """Minimal MCP JSON-RPC over HTTP (initialize / tools/list / tools/call / ping)."""
    authorization = request.headers.get("authorization")
    x_api_key = request.headers.get("x-api-key")
    x_office = request.headers.get("x-office-mcp-key")
    _require_key(authorization, x_api_key, x_office)

    try:
        msg = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"invalid json: {exc}") from exc

    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "quantum-office", "version": __version__},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        name = params.get("name") or ""
        arguments = params.get("arguments") or {}
        result = call_tool(name, arguments)
    elif method in {"notifications/initialized", "notifications/cancelled"}:
        return JSONResponse({"jsonrpc": "2.0", "result": None})
    else:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            },
            status_code=404,
        )

    return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": result})


def ensure_api_key_file(env_path: Path) -> str:
    """Ensure OFFICE_MCP_API_KEY exists in .env; return key (create if missing)."""
    key = (os.getenv("OFFICE_MCP_API_KEY") or "").strip()
    if key:
        return key
    key = secrets.token_urlsafe(32)
    lines: list[str] = []
    if env_path.is_file():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    # drop old empty assignment if any
    lines = [ln for ln in lines if not ln.startswith("OFFICE_MCP_API_KEY=")]
    lines.append(f"OFFICE_MCP_API_KEY={key}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    env_path.chmod(0o600)
    os.environ["OFFICE_MCP_API_KEY"] = key
    return key


if __name__ == "__main__":
    import uvicorn

    ensure_api_key_file(ROOT / ".env")
    load_dotenv(ROOT / ".env", override=True)
    globals()["API_KEY"] = (os.getenv("OFFICE_MCP_API_KEY") or "").strip()
    uvicorn.run(app, host=HOST, port=PORT)
