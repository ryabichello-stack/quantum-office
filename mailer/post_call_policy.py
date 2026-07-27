"""Post-call lead email policy (inbound only)."""

from __future__ import annotations


def is_outbound_call(payload: dict) -> bool:
    """True for AVA outbound / console dial calls (not inbound default)."""
    ctx = str(
        payload.get("context_name")
        or payload.get("context")
        or payload.get("ai_context")
        or ""
    ).strip().lower()
    if ctx in {"outbound", "out"}:
        return True
    direction = str(
        payload.get("call_direction")
        or payload.get("direction")
        or ""
    ).strip().lower()
    if direction in {"outbound", "out", "outgoing"}:
        return True
    flag = str(payload.get("outbound") or payload.get("aava_outbound") or "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    return False
