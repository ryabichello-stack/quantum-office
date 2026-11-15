"""Pending cabinet UI produced by MCP tool calls during a Hermes run.

Nous calls tools over HTTP (`call_mcp_tool`) in another request, so the operator
turn cannot see `pending_credential_form` on the tool result. We stash that UI
for the tenant (memory + `tenant.settings`) with a short TTL, then the chat
turn takes everything created after it started.

No Redis in this service. Settings JSON is already persisted; the in-process
bag covers the same worker and unit tests whose DB is a mock.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

UI_KEYS = (
    "pending_credential_form",
    "pending_confirmation",
    "pending_download",
    "pending_channel_chooser",
)
SETTINGS_KEY = "hermes_pending_ui"
TTL = timedelta(minutes=10)

# tenant_id -> [{at: datetime, tool: str, ui: dict}]
_memory: dict[str, list[dict[str, Any]]] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_at(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def ui_from_tool_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    ui: dict[str, Any] = {}
    for key in UI_KEYS:
        if payload.get(key):
            ui[key] = payload[key]
    if payload.get("needs_confirmation") and not ui.get("pending_confirmation"):
        ui["pending_confirmation"] = {
            "confirmation_id": payload.get("confirmation_id"),
            "tool_name": payload.get("tool_name"),
            "summary": payload.get("summary") or "",
            "params": payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
        }
    return ui


def stash_tool_ui(
    db: Session,
    tenant_id: UUID,
    tool_name: str,
    payload: dict[str, Any] | None,
) -> None:
    ui = ui_from_tool_payload(payload)
    if not ui:
        return
    now = _now()
    _memory.setdefault(str(tenant_id), []).append(
        {"at": now, "tool": tool_name, "ui": ui}
    )
    try:
        from app.models.tenant import Tenant

        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).one_or_none()
        raw = getattr(tenant, "settings", None) if tenant is not None else None
        if not isinstance(raw, dict):
            return
        settings = dict(raw)
        bag = [row for row in (settings.get(SETTINGS_KEY) or []) if isinstance(row, dict)]
        bag.append({"at": now.isoformat(), "tool": tool_name, "ui": ui})
        settings[SETTINGS_KEY] = bag[-30:]
        tenant.settings = settings
        flag_modified(tenant, "settings")
        db.add(tenant)
    except Exception:
        return


def take_pending_ui(db: Session, tenant_id: UUID, *, since: datetime) -> dict[str, Any]:
    """Merge and clear UI recorded at/after `since` (and drop expired leftovers)."""
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    # One-second slack so a tool that stamps just as the run starts is not lost.
    cutoff = since - timedelta(seconds=1)
    now = _now()
    merged: dict[str, Any] = {}
    _take_settings(db, tenant_id, cutoff=cutoff, now=now, merged=merged)
    _take_memory(str(tenant_id), cutoff=cutoff, now=now, merged=merged)
    return merged


def _fresh(at: datetime | None, *, now: datetime) -> bool:
    return bool(at) and (now - at) <= TTL


def _take_settings(
    db: Session,
    tenant_id: UUID,
    *,
    cutoff: datetime,
    now: datetime,
    merged: dict[str, Any],
) -> None:
    try:
        from app.models.tenant import Tenant

        tenant = (
            db.query(Tenant)
            .filter(Tenant.id == tenant_id)
            .execution_options(populate_existing=True)
            .one_or_none()
        )
        raw = getattr(tenant, "settings", None) if tenant is not None else None
        if not isinstance(raw, dict):
            return
        settings = dict(raw)
        bag = settings.get(SETTINGS_KEY) or []
        if not isinstance(bag, list):
            return
        keep: list[dict[str, Any]] = []
        for row in bag:
            if not isinstance(row, dict):
                continue
            at = _parse_at(row.get("at"))
            if not _fresh(at, now=now):
                continue
            if at >= cutoff:
                ui = row.get("ui")
                if isinstance(ui, dict):
                    merged.update(ui)
            else:
                keep.append(row)
        settings[SETTINGS_KEY] = keep
        tenant.settings = settings
        flag_modified(tenant, "settings")
        db.add(tenant)
        db.commit()
    except Exception:
        return


def _take_memory(
    key: str,
    *,
    cutoff: datetime,
    now: datetime,
    merged: dict[str, Any],
) -> None:
    items = _memory.pop(key, [])
    rest: list[dict[str, Any]] = []
    for row in items:
        at = row.get("at") if isinstance(row.get("at"), datetime) else None
        if not _fresh(at, now=now):
            continue
        if at >= cutoff:
            ui = row.get("ui")
            if isinstance(ui, dict):
                merged.update(ui)
        else:
            rest.append(row)
    if rest:
        _memory[key] = rest
