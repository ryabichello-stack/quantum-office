"""Filter MCP tools/list and authorize tools/call for scoped run tokens."""

from __future__ import annotations

from typing import Any

# Always-visible meta tools for a scoped run (readiness / profile without leaking full catalog).
META_ALWAYS = {
    "office.health",
    "office.connectors",
    "hermes.profile",
}


def filter_tools_catalog(catalog: list[dict[str, Any]], tool_ids: list[str] | None) -> list[dict[str, Any]]:
    """If tool_ids empty → deny-all except meta (fail closed for Nous runs).

    Empty grant list means the run has not been authorized for office tools yet.
    """
    allowed = {t.strip() for t in (tool_ids or []) if str(t).strip()}
    allowed |= META_ALWAYS
    return [t for t in catalog if t.get("name") in allowed]


def tool_allowed(name: str, tool_ids: list[str] | None) -> bool:
    n = (name or "").strip()
    if n in META_ALWAYS:
        return True
    allowed = {t.strip() for t in (tool_ids or []) if str(t).strip()}
    return n in allowed
