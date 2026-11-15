"""Map Hermes 0.23 run SSE into cabinet actions. No secrets, no raw tool ids in labels."""

from __future__ import annotations

import json
import re
from typing import Any, Iterator

_SECRET_MARKERS = ("password", "token", "api_key", "secret", "authorization", "bearer ")

_PREFIXES = (
    "web_",
    "phones_",
    "telephony_",
    "credentials_",
    "hermes_",
    "files_",
    "crm_",
    "calls_",
    "billing_",
    "channels_",
    "channel_",
    "office_",
)


def normalize_tool_name(raw: str | None) -> str:
    name = (raw or "").strip()
    if not name:
        return ""
    name = re.sub(r"^mcp__delno_office__", "", name)
    name = re.sub(r"^mcp__", "", name)
    if "." not in name:
        for prefix in _PREFIXES:
            if name.startswith(prefix):
                name = prefix[:-1] + "." + name[len(prefix) :]
                break
    return name[:120]


def safe_preview(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    low = text.lower()
    if any(marker in low for marker in _SECRET_MARKERS):
        return None
    return text[:160]


def parse_sse_block(block: str) -> tuple[str | None, dict[str, Any] | None]:
    event_name: str | None = None
    data_lines: list[str] = []
    for raw in block.splitlines():
        line = raw.strip("\r")
        if not line or line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip() or None
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if not data_lines and not event_name:
        return None, None
    payload: dict[str, Any] = {}
    if data_lines:
        raw_data = "\n".join(data_lines).strip()
        if raw_data and raw_data != "[DONE]":
            try:
                parsed = json.loads(raw_data)
            except json.JSONDecodeError:
                parsed = {"preview": raw_data}
            if isinstance(parsed, dict):
                payload = parsed
    return event_name, payload


def iter_sse_blocks(chunks: Iterator[str]) -> Iterator[tuple[str | None, dict[str, Any]]]:
    buf = ""
    for chunk in chunks:
        buf += chunk
        while "\n\n" in buf:
            block, buf = buf.split("\n\n", 1)
            name, data = parse_sse_block(block)
            if data is None and not name:
                continue
            yield name, data or {}
    if buf.strip():
        name, data = parse_sse_block(buf)
        if name or data:
            yield name, data or {}


def map_hermes_event(event_name: str | None, data: dict[str, Any] | None) -> dict[str, Any] | None:
    body = data or {}
    kind = str(event_name or body.get("type") or body.get("event") or "").strip()
    tool = normalize_tool_name(str(body.get("tool") or body.get("name") or body.get("tool_name") or ""))
    preview = safe_preview(body.get("preview") or body.get("summary") or "")
    call_id = str(body.get("tool_call_id") or body.get("id") or "").strip()[:80]
    if kind in {"tool.started", "tool_started"}:
        return {"phase": "tool", "tool": tool, "preview": preview, "tool_call_id": call_id or None}
    if kind in {"tool.completed", "tool_completed", "tool.failed"}:
        return {"phase": "between", "tool": tool, "tool_call_id": call_id or None}
    if kind in {"reasoning.available", "reasoning", "reasoning.delta"}:
        return {"phase": "thinking"}
    if kind in {"subagent.start", "subagent.started"}:
        return {
            "phase": "tool",
            "tool": tool or "hermes.agent_run",
            "preview": preview,
            "tool_call_id": call_id or None,
        }
    if kind in {"subagent.complete", "subagent.completed"}:
        return {"phase": "between", "tool": tool, "tool_call_id": call_id or None}
    terminal = kind.rsplit(".", 1)[-1] if kind else ""
    status = str(body.get("status") or "").lower()
    if kind.startswith("run.") and terminal in {"completed", "failed", "error", "cancelled", "canceled", "stopped"}:
        return {"phase": "terminal", "status": terminal}
    if status in {"completed", "failed", "error", "cancelled", "canceled", "stopped"} and kind in {"", "run", "done"}:
        return {"phase": "terminal", "status": status}
    return None


def format_sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def tenant_may_read_run(*, owner_tenant_id: str, caller_tenant_id: str, stored_run_id: str, requested_id: str) -> bool:
    if not owner_tenant_id or not caller_tenant_id or not stored_run_id or not requested_id:
        return False
    if str(owner_tenant_id) != str(caller_tenant_id):
        return False
    return str(stored_run_id) == str(requested_id)
