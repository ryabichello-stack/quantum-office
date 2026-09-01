"""Cursor MCP stdio server for Second Brain (A2).

Tools: kb.search, kb.get, kb.related, kb.ingest_status,
       kb.find_contact, kb.list_threads

Speaks MCP JSON-RPC over stdio with Content-Length framing (no extra deps).
"""

from __future__ import annotations

import json
import sys
from typing import Any

from brain_platform.mcp.client import brain_request

SERVER_INFO = {"name": "quantum-brain", "version": "0.2.0"}
PROTOCOL_VERSION = "2024-11-05"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "kb.search",
        "description": (
            "Second Brain hybrid search (FAQ, mail, files, vault) with ACL. "
            "Returns text + citations."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 8},
                "mode": {
                    "type": "string",
                    "enum": ["hybrid", "keyword", "semantic"],
                    "default": "hybrid",
                },
                "max_chars": {"type": "integer", "default": 6000},
            },
            "required": ["query"],
        },
    },
    {
        "name": "kb.get",
        "description": "Fetch one document or chunk by id (ACL enforced).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "chunk_id": {"type": "string"},
                "max_chars": {"type": "integer", "default": 12000},
            },
        },
    },
    {
        "name": "kb.related",
        "description": (
            "Expand knowledge graph around a person/company/topic "
            "(works_at, participant_of, owns_doc)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string"},
                "entity_id": {"type": "string"},
                "depth": {"type": "integer", "default": 1},
                "limit": {"type": "integer", "default": 40},
            },
        },
    },
    {
        "name": "kb.ingest_status",
        "description": "Last ingest markers + corpus stats.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "kb.find_contact",
        "description": "Find office contacts by name/email/phone/company.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string"},
                "company": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "kb.list_threads",
        "description": "List email threads by subject/topic.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string"},
                "since": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
]


def _tool_result(payload: Any) -> dict[str, Any]:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": text}]}


def call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    args = arguments or {}
    if name == "kb.search":
        return _tool_result(
            brain_request(
                "POST",
                "/api/brain/search",
                {
                    "query": args.get("query") or "",
                    "limit": int(args.get("limit") or 8),
                    "mode": args.get("mode") or "hybrid",
                    "max_chars": int(args.get("max_chars") or 6000),
                },
            )
        )
    if name == "kb.get":
        return _tool_result(
            brain_request(
                "POST",
                "/api/brain/get",
                {
                    "document_id": args.get("document_id"),
                    "chunk_id": args.get("chunk_id"),
                    "max_chars": int(args.get("max_chars") or 12000),
                },
            )
        )
    if name == "kb.related":
        return _tool_result(
            brain_request(
                "POST",
                "/api/brain/graph/expand",
                {
                    "q": args.get("q") or "",
                    "entity_id": args.get("entity_id"),
                    "depth": int(args.get("depth") or 1),
                    "limit": int(args.get("limit") or 40),
                },
            )
        )
    if name == "kb.ingest_status":
        return _tool_result(brain_request("GET", "/api/brain/ingest/status"))
    if name == "kb.find_contact":
        return _tool_result(
            brain_request(
                "POST",
                "/api/brain/contacts/find",
                {
                    "q": args.get("q") or "",
                    "email": args.get("email") or "",
                    "phone": args.get("phone") or "",
                    "company": args.get("company") or "",
                    "limit": int(args.get("limit") or 20),
                },
            )
        )
    if name == "kb.list_threads":
        return _tool_result(
            brain_request(
                "POST",
                "/api/brain/threads/list",
                {
                    "q": args.get("q") or "",
                    "since": args.get("since"),
                    "limit": int(args.get("limit") or 20),
                },
            )
        )
    return {
        "content": [{"type": "text", "text": f"unknown tool: {name}"}],
        "isError": True,
    }


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
    return json.loads(body.decode("utf-8"))


def _write_message(msg: dict[str, Any]) -> None:
    data = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(data)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def _handle(msg: dict[str, Any]) -> dict[str, Any] | None:
    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    # notifications have no id
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
