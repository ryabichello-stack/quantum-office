"""Human-readable conversation previews for Console calls table."""

from __future__ import annotations

import json
from typing import Any


def role_label(role: str) -> str:
    r = (role or "").strip().lower()
    return {
        "user": "Клиент",
        "assistant": "AVA",
        "system": "Система",
        "tool": "Tool",
    }.get(r, role or "?")


def format_transcript_preview(hist_raw: Any, limit: int = 320) -> str:
    """Human-readable turn preview instead of raw JSON substr."""
    turns: Any
    if isinstance(hist_raw, list):
        turns = hist_raw
    elif isinstance(hist_raw, str):
        text = hist_raw.strip()
        if not text:
            return ""
        try:
            turns = json.loads(text)
        except json.JSONDecodeError:
            return text[:limit] + ("…" if len(text) > limit else "")
    else:
        return ""
    if not isinstance(turns, list):
        return str(turns)[:limit]
    parts: list[str] = []
    for item in turns:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or item.get("text") or "").strip()
        if not content:
            continue
        parts.append(f"{role_label(str(item.get('role') or ''))}: {content}")
    joined = " · ".join(parts)
    if len(joined) <= limit:
        return joined
    return joined[: limit - 1] + "…"
