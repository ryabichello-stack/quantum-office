"""Cursor / Claude / Grok MCP stdio server for Quantum Office.

Speaks MCP JSON-RPC over stdio with Content-Length framing (no extra deps).
"""

from __future__ import annotations

import json
import sys
from typing import Any

from quantum_office_mcp import __version__
from quantum_office_mcp.client import (
    calendar_base,
    calendar_request,
    campaign_base,
    campaign_request,
    conference_base,
    console_base,
    console_request,
    files_base,
    health_probe,
    knowledge_base,
    knowledge_request,
    mailer_base,
    outreach_base,
    outreach_request,
    text_bot_base,
)
from quantum_office_mcp.script_builder import build_task_prompt

SERVER_INFO = {"name": "quantum-office", "version": __version__}
PROTOCOL_VERSION = "2024-11-05"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "office.health",
        "description": (
            "Probe /health for office services (console, campaign, knowledge, "
            "calendar, conference, files, outreach, text-bot, mailer)."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "office.status",
        "description": (
            "Full Quantum Console status: Asterisk/Mango, outbound, units, "
            "line, campaign glance."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "line.get",
        "description": "Get inbound auto-line state (AstDB quantum/inbound_line).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "line.set",
        "description": "Enable or disable inbound auto-line (Busy when off).",
        "inputSchema": {
            "type": "object",
            "properties": {"enabled": {"type": "boolean"}},
            "required": ["enabled"],
        },
    },
    {
        "name": "calls.list_tools",
        "description": "Catalog of in-call tools available for outbound dial.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "calls.dial",
        "description": (
            "Originate one outbound AVA call. Pass per-call greeting/script/tools "
            "without changing global YAML. Requires CONSOLE_TOKEN + OUTBOUND_ENABLED."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "greeting": {"type": "string"},
                "script": {"type": "string"},
                "tools": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "use_knowledge": {"type": "boolean", "default": False},
                "context": {"type": "string", "default": "outbound"},
                "provider": {"type": "string"},
                "caller_id_num": {"type": "string"},
                "caller_id_name": {"type": "string"},
            },
            "required": ["phone"],
        },
    },
    {
        "name": "calls.assign_task",
        "description": (
            "High-level sales task: build LPR/qualification playbook from structured "
            "fields and dial immediately. Prefer this for Grok/sales bots."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "company": {"type": "string"},
                "contact_name": {"type": "string"},
                "goal": {
                    "type": "string",
                    "description": "Desired outcome of the call",
                },
                "product": {"type": "string"},
                "notes": {"type": "string"},
                "find_lpr": {"type": "boolean", "default": True},
                "book_meeting": {"type": "boolean", "default": True},
                "language": {"type": "string", "default": "ru"},
                "greeting": {"type": "string"},
                "script": {
                    "type": "string",
                    "description": "Optional full playbook override",
                },
                "tools": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "use_knowledge": {"type": "boolean", "default": True},
                "context": {"type": "string", "default": "outbound"},
            },
            "required": ["phone"],
        },
    },
    {
        "name": "calls.callback",
        "description": (
            "Outbound via Mango VPBX callback (extension answers → PSTN). "
            "Use when SIP PSTN originate is blocked."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "extension": {"type": "string"},
                "line_number": {"type": "string"},
                "command_id": {"type": "string"},
            },
            "required": ["phone"],
        },
    },
    {
        "name": "calls.list",
        "description": "List recent call records (transcripts truncated in list).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
                "context": {
                    "type": "string",
                    "description": "Filter by context_name, e.g. outbound",
                },
            },
        },
    },
    {
        "name": "calls.get",
        "description": "Full transcript + tools for one call_id.",
        "inputSchema": {
            "type": "object",
            "properties": {"call_id": {"type": "string"}},
            "required": ["call_id"],
        },
    },
    {
        "name": "campaign.status",
        "description": "Sheets-campaign worker status/progress.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "campaign.preview",
        "description": "Preview sheet leads without marks (candidates to dial).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 30},
                "sheet": {"type": "string"},
            },
        },
    },
    {
        "name": "campaign.results",
        "description": "Local campaign dial results (even without Sheets writeback).",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 40}},
        },
    },
    {
        "name": "campaign.start",
        "description": "Start Sheets campaign worker.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_calls": {"type": "integer", "default": 5},
                "sheet": {"type": "string"},
                "dry_run": {"type": "boolean"},
            },
        },
    },
    {
        "name": "campaign.stop",
        "description": "Stop Sheets campaign worker.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "campaign.get_script",
        "description": "Get Sheets-campaign greeting + playbook.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "campaign.set_script",
        "description": "Update Sheets-campaign greeting/script/tools.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "greeting": {"type": "string"},
                "script": {"type": "string"},
                "tools": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
    },
    {
        "name": "kb.search",
        "description": "Second Brain hybrid search (FAQ, mail, files, vault).",
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
        "description": "Fetch one Second Brain document/chunk by id.",
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
        "name": "calendar.check",
        "description": "Check if a calendar slot is free.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "ISO datetime"},
                "timezone": {"type": "string"},
            },
            "required": ["start"],
        },
    },
    {
        "name": "calendar.suggest",
        "description": "Suggest free calendar slots near desired start.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start": {"type": "string"},
                "timezone": {"type": "string"},
                "duration_min": {"type": "integer"},
                "suggestions_count": {"type": "integer"},
                "search_hours_ahead": {"type": "integer"},
            },
            "required": ["start"],
        },
    },
    {
        "name": "calendar.create",
        "description": "Create a calendar event (optionally with Telemost via conference).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start": {"type": "string"},
                "end": {"type": "string"},
                "summary": {"type": "string"},
                "description": {"type": "string"},
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "timezone": {"type": "string"},
                "create_conference": {"type": "boolean"},
            },
            "required": ["start", "summary"],
        },
    },
    {
        "name": "outreach.dashboard",
        "description": "Outreach email campaign dashboard metrics.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "outreach.status",
        "description": "Lightweight outreach /status endpoint.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "outreach.packs",
        "description": "List industry email packs (lombards, MFO, …).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "outreach.outbox",
        "description": "List outreach outbox rows (queued/sent).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 30},
                "status": {"type": "string"},
            },
        },
    },
]


def _tool_result(payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=2)
    out: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if is_error:
        out["isError"] = True
    return out


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    args = arguments or {}

    if name == "office.health":
        targets = {
            "console": console_base(),
            "campaign": campaign_base(),
            "knowledge": knowledge_base(),
            "calendar": calendar_base(),
            "conference": conference_base(),
            "files": files_base(),
            "outreach": outreach_base(),
            "text_bot": text_bot_base(),
            "mailer": mailer_base(),
        }
        services = {k: health_probe(v) for k, v in targets.items()}
        ok = all(bool(v.get("ok")) for v in services.values())
        return _tool_result({"ok": ok, "services": services})

    if name == "office.status":
        return _tool_result(console_request("GET", "/api/status"))

    if name == "line.get":
        return _tool_result(console_request("GET", "/api/line"))

    if name == "line.set":
        return _tool_result(
            console_request("POST", "/api/line", {"enabled": _as_bool(args.get("enabled"))})
        )

    if name == "calls.list_tools":
        return _tool_result(console_request("GET", "/api/tools"))

    if name == "calls.dial":
        phone = (args.get("phone") or "").strip()
        if not phone:
            return _tool_result({"ok": False, "error": "phone required"}, is_error=True)
        body: dict[str, Any] = {"phone": phone}
        for key in (
            "greeting",
            "script",
            "context",
            "provider",
            "caller_id_num",
            "caller_id_name",
        ):
            if args.get(key) is not None and str(args.get(key)).strip() != "":
                body[key] = args[key]
        if isinstance(args.get("tools"), list):
            body["tools"] = args["tools"]
        if "use_knowledge" in args:
            body["use_knowledge"] = _as_bool(args.get("use_knowledge"))
        return _tool_result(console_request("POST", "/api/outbound/dial", body, timeout=45))

    if name == "calls.assign_task":
        phone = (args.get("phone") or "").strip()
        if not phone:
            return _tool_result({"ok": False, "error": "phone required"}, is_error=True)
        built = build_task_prompt(args)
        body = {
            "phone": phone,
            "greeting": built["greeting"],
            "script": built["script"],
            "tools": built["tools"],
            "use_knowledge": built["use_knowledge"],
            "context": (args.get("context") or "outbound"),
        }
        dial = console_request("POST", "/api/outbound/dial", body, timeout=45)
        return _tool_result({"task": built, "dial": dial})

    if name == "calls.callback":
        phone = (args.get("phone") or "").strip()
        if not phone:
            return _tool_result({"ok": False, "error": "phone required"}, is_error=True)
        body = {"phone": phone}
        for key in ("extension", "line_number", "command_id"):
            if args.get(key):
                body[key] = args[key]
        return _tool_result(console_request("POST", "/api/outbound/callback", body, timeout=45))

    if name == "calls.list":
        return _tool_result(
            console_request(
                "GET",
                "/api/calls",
                query={
                    "limit": int(args.get("limit") or 20),
                    "context": args.get("context"),
                },
            )
        )

    if name == "calls.get":
        call_id = (args.get("call_id") or "").strip()
        if not call_id:
            return _tool_result({"ok": False, "error": "call_id required"}, is_error=True)
        return _tool_result(console_request("GET", f"/api/calls/{call_id}"))

    if name == "campaign.status":
        return _tool_result(campaign_request("GET", "/api/campaign/status"))

    if name == "campaign.preview":
        return _tool_result(
            campaign_request(
                "GET",
                "/api/campaign/preview",
                query={"limit": int(args.get("limit") or 30), "sheet": args.get("sheet")},
            )
        )

    if name == "campaign.results":
        return _tool_result(
            campaign_request(
                "GET",
                "/api/campaign/results",
                query={"limit": int(args.get("limit") or 40)},
            )
        )

    if name == "campaign.start":
        body = {"max_calls": int(args.get("max_calls") or 5)}
        if args.get("sheet"):
            body["sheet"] = args["sheet"]
        if "dry_run" in args:
            body["dry_run"] = _as_bool(args.get("dry_run"))
        return _tool_result(campaign_request("POST", "/api/campaign/start", body))

    if name == "campaign.stop":
        return _tool_result(campaign_request("POST", "/api/campaign/stop", {}))

    if name == "campaign.get_script":
        return _tool_result(campaign_request("GET", "/api/campaign/script"))

    if name == "campaign.set_script":
        body = {}
        for key in ("greeting", "script", "tools"):
            if key in args and args[key] is not None:
                body[key] = args[key]
        return _tool_result(campaign_request("PUT", "/api/campaign/script", body))

    if name == "kb.search":
        return _tool_result(
            knowledge_request(
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
            knowledge_request(
                "POST",
                "/api/brain/get",
                {
                    "document_id": args.get("document_id"),
                    "chunk_id": args.get("chunk_id"),
                    "max_chars": int(args.get("max_chars") or 12000),
                },
            )
        )

    if name == "calendar.check":
        body = {"start": args.get("start")}
        if args.get("timezone"):
            body["timezone"] = args["timezone"]
        return _tool_result(calendar_request("POST", "/api/calendar/check", body))

    if name == "calendar.suggest":
        body = {"start": args.get("start")}
        for key in ("timezone", "duration_min", "suggestions_count", "search_hours_ahead"):
            if args.get(key) is not None:
                body[key] = args[key]
        return _tool_result(calendar_request("POST", "/api/calendar/suggest", body))

    if name == "calendar.create":
        body = {
            "start": args.get("start"),
            "summary": args.get("summary"),
        }
        for key in ("end", "description", "attendees", "timezone", "create_conference"):
            if args.get(key) is not None:
                body[key] = args[key]
        return _tool_result(calendar_request("POST", "/api/calendar/create", body))

    if name == "outreach.dashboard":
        return _tool_result(outreach_request("GET", "/api/dashboard"))

    if name == "outreach.status":
        return _tool_result(outreach_request("GET", "/status"))

    if name == "outreach.packs":
        return _tool_result(outreach_request("GET", "/api/packs"))

    if name == "outreach.outbox":
        return _tool_result(
            outreach_request(
                "GET",
                "/api/outbox",
                query={
                    "limit": int(args.get("limit") or 30),
                    "status": args.get("status"),
                },
            )
        )

    return _tool_result(f"unknown tool: {name}", is_error=True)


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
