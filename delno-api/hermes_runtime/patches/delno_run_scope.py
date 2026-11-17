"""DELNO run identity for the current Hermes turn, never process-global.

This module is copied into upstream Hermes's ``tools`` package at image build.
Only the API-server run handler may bind it. The model cannot choose a tenant,
run, profile, or credential in tool arguments.
"""

from __future__ import annotations

import json
import os
from contextvars import ContextVar, Token
from dataclasses import dataclass, field

import httpx


@dataclass(frozen=True)
class DelnoRunScope:
    token: str = field(repr=False)
    run_id: str
    profile_id: str


_scope: ContextVar[DelnoRunScope | None] = ContextVar("delno_mcp_run_scope", default=None)


def scoped_mode_enabled() -> bool:
    return (os.environ.get("DELNO_MCP_RUN_SCOPE_ENABLED") or "").strip().lower() in (
        "1", "true", "yes",
    )


def bind_run_scope(*, token: str, run_id: str, profile_id: str) -> Token:
    return _scope.set(DelnoRunScope(token=token, run_id=run_id, profile_id=profile_id))


def reset_run_scope(reset_token: Token) -> None:
    _scope.reset(reset_token)


def current_run_scope() -> DelnoRunScope | None:
    return _scope.get()


def call_tool(name: str, arguments: dict, *, timeout: float) -> str:
    """Call only DELNO's internal MCP endpoint with this turn's scoped token.

    Connections discovered with the legacy profile key remain useful for the
    tool schema. They are never used to execute a business tool in this path.
    """
    scope = current_run_scope()
    if scope is None or not all((scope.token, scope.run_id, scope.profile_id)):
        return json.dumps({"error": "delno_run_scope_missing"})
    url = (os.environ.get("DELNO_MCP_TOOLS_CALL_URL") or
           "http://delno-api:8020/v1/mcp/tools/call").strip()
    if url != "http://delno-api:8020/v1/mcp/tools/call":
        # An egress override is not allowed in a shared tenant worker.
        return json.dumps({"error": "delno_mcp_endpoint_invalid"})
    try:
        with httpx.Client(trust_env=False, follow_redirects=False,
                          timeout=max(1.0, min(float(timeout), 120.0))) as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {scope.token}",
                    "X-Delno-Run-Id": scope.run_id,
                    "X-Delno-Profile-Id": scope.profile_id,
                },
                json={"name": name, "arguments": arguments},
            )
        if response.status_code != 200:
            return json.dumps({"error": "delno_mcp_rejected", "status": response.status_code})
        if len(response.content) > 1024 * 1024:
            return json.dumps({"error": "delno_mcp_response_too_large"})
        payload = response.json()
        if not isinstance(payload, dict):
            return json.dumps({"error": "delno_mcp_invalid_response"})
        return json.dumps(payload.get("result", payload), ensure_ascii=False)
    except (httpx.HTTPError, ValueError, TypeError):
        return json.dumps({"error": "delno_mcp_transport_error"})
