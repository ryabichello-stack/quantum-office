"""Compatibility façade over placement (tenant → profile → worker).

Legacy name kept so onboarding / tests keep importing assign_isolated_runtime.
Combat default: one multiplex pool gateway for all companies
(HERMES_WORKER_MAX_PROFILES, default 256).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.services.hermes_nous.placement import (
    PlacementError,
    ensure_tenant_placement,
    ensure_worker_catalog,
    list_placement_snapshot,
    resolve_placement,
)


def list_runtime_slots() -> list[dict[str, str]]:
    """Diagnostic list of configured workers (combat: single pool)."""
    import os

    return [
        {
            "id": "pool",
            "base_url": os.environ.get("HERMES_NOUS_RUNTIME_URL")
            or "http://delno-hermes-pool:8642",
            "api_server_key_env": "HERMES_API_SERVER_KEY",
            "mcp_key_env": "DELNO_MCP_KEY",
        },
    ]


def assign_isolated_runtime(
    db: Session, ctx: TenantContext, *, prefer_slot: str | None = None
) -> dict[str, Any]:
    """Ensure company_main profile exists and is placed on the pool when possible."""
    ensure_worker_catalog(db)
    try:
        profile = ensure_tenant_placement(db, ctx, prefer_worker_id=prefer_slot)
    except PlacementError as exc:
        return {
            "ok": False,
            "error": exc.code,
            "status": "unavailable",
            "detail": exc.detail,
            "isolation": "multiplex_profiles",
        }
    base_url = None
    if profile.worker_id and profile.status == "ready":
        from app.models.hermes_runtime import HermesWorker

        w = db.query(HermesWorker).filter(HermesWorker.worker_id == profile.worker_id).one_or_none()
        if w:
            base_url = f"{w.base_url.rstrip('/')}/p/{profile.profile_id}"
    return {
        "ok": True,
        "slot_id": profile.worker_id,
        "worker_id": profile.worker_id,
        "profile_id": profile.profile_id,
        "agent_id": profile.agent_id,
        "runtime_base_url": base_url,
        "api_path_prefix": f"/p/{profile.profile_id}" if profile.profile_id else None,
        "api_server_key_env": profile.credential_ref,
        "status": profile.status,
        "state_location": profile.state_location,
        "isolation": "multiplex_profiles",
        "pin": profile.pin,
    }


def ensure_tenant_runtime(db: Session, ctx: TenantContext) -> dict[str, Any]:
    """Idempotent placement; raises PlacementError when not ready for traffic."""
    out = assign_isolated_runtime(db, ctx)
    if out.get("status") != "ready" or not out.get("worker_id"):
        raise PlacementError(
            "hermes_runtime_provisioning",
            status=503,
            detail={
                "profile_id": out.get("profile_id"),
                "status": out.get("status"),
                "hint": "No free worker capacity — do not fall back to another tenant runtime.",
            },
        )
    return resolve_placement(db, ctx)["record"]


def placement_snapshot(db: Session) -> dict[str, Any]:
    return list_placement_snapshot(db)
