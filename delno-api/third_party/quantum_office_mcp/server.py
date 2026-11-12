"""Cursor / Claude / Grok MCP stdio server for Quantum Office.

Speaks MCP JSON-RPC over stdio with Content-Length framing (no extra deps).
"""

from __future__ import annotations

import sys
from typing import Any

from quantum_office_mcp import __version__
from quantum_office_mcp.handlers import call_tool
from quantum_office_mcp.tools import TOOLS

# Re-export for tests / `from quantum_office_mcp.server import TOOLS, call_tool, _handle`
__all__ = ["TOOLS", "call_tool", "_handle", "main", "SERVER_INFO"]

SERVER_INFO = {"name": "quantum-office", "version": __version__}
PROTOCOL_VERSION = "2024-11-05"


def _read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        decoded = line.decode("utf-8", errors="replace")
        if ":" not in decoded:
            continue
        key, value = decoded.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length") or 0)
    if length <= 0:
        return None
    body = sys.stdin.buffer.read(length)
    if not body:
        return None
    import json

    return json.loads(body.decode("utf-8"))


def _write_message(msg: dict[str, Any]) -> None:
    import json

    data = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(data)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def _handle(msg: dict[str, Any]) -> dict[str, Any] | None:
    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    if method == "notifications/initialized":
        return None
    if method == "notifications/cancelled":
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name") or ""
        arguments = params.get("arguments") or {}
        result = call_tool(name, arguments)
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    if msg_id is None:
        return None
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> int:
    while True:
        msg = _read_message()
        if msg is None:
            return 0
        try:
            resp = _handle(msg)
        except Exception as exc:  # noqa: BLE001
            if msg.get("id") is not None:
                _write_message(
                    {
                        "jsonrpc": "2.0",
                        "id": msg.get("id"),
                        "error": {"code": -32000, "message": str(exc)},
                    }
                )
            continue
        if resp is not None:
            _write_message(resp)


if __name__ == "__main__":
    raise SystemExit(main())
