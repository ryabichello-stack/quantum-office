"""tenant_id → profile_id → worker_id placement (source of truth).

Rules (owner, 2026-11-13+):
- Never silently route a tenant to another company's worker/profile.
- Never assign two open writers to the same profile home.
- Workers are multiplex pool nodes: each hosts many company profiles under
  HERMES_PROFILES_ROOT/workers/<worker_id>/profiles/<profile_id> (Hermes /p/<id>/).
- Capacity per worker: HERMES_WORKER_MAX_PROFILES (default 64). When pool full →
  status=provisioning/unavailable — do NOT fall back to slots[0]/A.
- Public api.dlno.ru is SNI-routed; Hermes MCP must use internal DELNO URL.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.hermes_runtime import HermesProfile, HermesWorker
from app.models.tenant import Tenant
from app.services.hermes_nous.profile_homes import ensure_live_profile_home, worker_bind_hint
from app.services.hermes_nous.provision import ensure_tenant_hermes_home, hermes_home_path
from app.services.hermes_nous.provision import _internal_mcp_url
from app.services.mcp_gateway import ensure_mcp_api_key

PIN = "v0.23.1"
AGENT_COMPANY_MAIN = "company_main"


def default_max_profiles() -> int:
    raw = (os.environ.get("HERMES_WORKER_MAX_PROFILES") or "64").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 64
    return max(1, n)


# Pool sticky IDs (not tenant names). Env can override catalog / capacity.
_DEFAULT_WORKERS = (
    {
        "worker_id": "tenant-a",
        "base_url_env": "HERMES_NOUS_RUNTIME_URL",
        "base_url_default": "http://delno-hermes-tenant-a:8642",
        "api_server_key_env": "HERMES_API_SERVER_KEY",
    },
    {
        "worker_id": "tenant-b",
        "base_url_env": "HERMES_NOUS_RUNTIME_URL_B",
        "base_url_default": "http://delno-hermes-tenant-b:8642",
        "api_server_key_env": "HERMES_API_SERVER_KEY_B",
    },
)


class PlacementError(RuntimeError):
    def __init__(self, code: str, *, status: int = 503, detail: dict[str, Any] | None = None):
        super().__init__(code)
        self.code = code
        self.status = status
        self.detail = detail or {}


def profile_id_for_tenant(slug: str, *, agent_id: str = AGENT_COMPANY_MAIN) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in (slug or "tenant").lower())
    return f"tenant_{safe}__{agent_id}"


def _worker_api_key(spec_or_row: dict[str, Any] | HermesWorker) -> str:
    if isinstance(spec_or_row, HermesWorker):
        env_name = spec_or_row.api_server_key_env or ""
    else:
        env_name = str(spec_or_row.get("api_server_key_env") or "")
    return (os.environ.get(env_name) or "").strip()


def ensure_worker_catalog(db: Session) -> list[HermesWorker]:
    """Upsert pool workers from env. Idempotent; refreshes max_profiles from env."""
    out: list[HermesWorker] = []
    cap = default_max_profiles()
    for spec in _DEFAULT_WORKERS:
        wid = spec["worker_id"]
        row = db.query(HermesWorker).filter(HermesWorker.worker_id == wid).one_or_none()
        base = (os.environ.get(spec["base_url_env"]) or spec["base_url_default"]).rstrip("/")
        if row is None:
            row = HermesWorker(
                worker_id=wid,
                base_url=base,
                api_server_key_env=spec["api_server_key_env"],
                status="ready",
                max_profiles=cap,
                image_digest=os.environ.get("HERMES_IMAGE_DIGEST") or None,
                meta={
                    "source": "default_catalog",
                    "isolation": "multiplex_profiles",
                    "layout": "workers/<id>/profiles/<profile_id>",
                },
            )
            db.add(row)
        else:
            row.base_url = base
            row.api_server_key_env = spec["api_server_key_env"]
            row.max_profiles = cap
            meta = dict(row.meta or {})
            meta["isolation"] = "multiplex_profiles"
            meta["layout"] = "workers/<id>/profiles/<profile_id>"
            row.meta = meta
        out.append(row)
    db.commit()
    for row in out:
        db.refresh(row)
    return out


def _worker_open_profile_count(db: Session, worker_id: str) -> int:
    return (
        db.query(HermesProfile)
        .filter(
            HermesProfile.worker_id == worker_id,
            HermesProfile.status.in_(("ready", "provisioning", "assigned")),
        )
        .count()
    )


def _pick_free_worker(db: Session) -> HermesWorker | None:
    """Least-loaded ready worker with free multiplex capacity."""
    ensure_worker_catalog(db)
    workers = (
        db.query(HermesWorker)
        .filter(HermesWorker.status == "ready")
        .order_by(HermesWorker.worker_id.asc())
        .all()
    )
    ranked: list[tuple[int, str, HermesWorker]] = []
    for w in workers:
        cap = w.max_profiles
        if cap is None:
            # Explicit unlimited
            open_n = _worker_open_profile_count(db, w.worker_id)
            ranked.append((open_n, w.worker_id, w))
            continue
        open_n = _worker_open_profile_count(db, w.worker_id)
        if open_n < int(cap):
            ranked.append((open_n, w.worker_id, w))
    if not ranked:
        return None
    ranked.sort(key=lambda t: (t[0], t[1]))
    return ranked[0][2]


def _mirror_settings_runtime(db: Session, tenant: Tenant, profile: HermesProfile, worker: HermesWorker | None) -> None:
    """Keep legacy tenant.settings.hermes_nous.runtime in sync for diagnostics."""
    settings = dict(tenant.settings) if isinstance(tenant.settings, dict) else {}
    nous = dict(settings.get("hermes_nous") or {})
    runtime = dict(nous.get("runtime") or {})
    prefix = f"/p/{profile.profile_id}" if profile.profile_id else ""
    runtime.update(
        {
            "engine": "nous_hermes_agent",
            "pin": profile.pin,
            "profile_id": profile.profile_id,
            "agent_id": profile.agent_id,
            "slot_id": worker.worker_id if worker else None,
            "worker_id": worker.worker_id if worker else None,
            "runtime_base_url": (
                f"{worker.base_url.rstrip('/')}{prefix}" if worker else None
            ),
            "api_path_prefix": prefix or None,
            "api_server_key_env": (worker.api_server_key_env if worker else profile.credential_ref)
            or "HERMES_API_SERVER_KEY",
            "hermes_home": profile.state_location,
            "state_location": profile.state_location,
            "status": profile.status,
            "isolation": "multiplex_profiles",
            "placement": "hermes_profiles",
        }
    )
    nous["runtime"] = runtime
    settings["hermes_nous"] = nous
    tenant.settings = settings
    db.add(tenant)


def get_company_profile(db: Session, tenant_id: UUID) -> HermesProfile | None:
    return (
        db.query(HermesProfile)
        .filter(
            HermesProfile.tenant_id == tenant_id,
            HermesProfile.agent_id == AGENT_COMPANY_MAIN,
        )
        .one_or_none()
    )


def ensure_tenant_placement(
    db: Session,
    ctx: TenantContext,
    *,
    prefer_worker_id: str | None = None,
    allow_provision_without_worker: bool = True,
) -> HermesProfile:
    """Create/return the company_main profile. Assign a free multiplex worker when available.

    Does NOT steal another tenant's profile. If pool is full → status=provisioning
    (or unavailable) and no runtime_base_url — caller must surface that honestly.
    """
    ensure_worker_catalog(db)
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    tenant_mcp_key = ensure_mcp_api_key(db, tenant)
    db.refresh(tenant)

    # API-side skeleton (backup) + worker-visible live home (shared volume).
    ensure_tenant_hermes_home(db, ctx)
    db.refresh(tenant)

    profile = get_company_profile(db, ctx.tenant_id)
    pid = profile_id_for_tenant(tenant.slug)
    api_home = str(hermes_home_path(ctx.tenant_id))

    if profile is None:
        profile = HermesProfile(
            tenant_id=ctx.tenant_id,
            profile_id=pid,
            agent_id=AGENT_COMPANY_MAIN,
            state_location=api_home,
            status="provisioning",
            pin=PIN,
            actor_user_id=ctx.user_id,
            meta={
                "api_skeleton_home": api_home,
                "note": "state_location becomes workers/<id>/profiles/<profile_id> when placed",
            },
        )
        db.add(profile)
        db.flush()

    # Sticky worker: keep assignment if still valid.
    worker: HermesWorker | None = None
    if profile.worker_id:
        worker = db.query(HermesWorker).filter(HermesWorker.worker_id == profile.worker_id).one_or_none()
        if worker is None or worker.status == "offline":
            profile.worker_id = None
            profile.credential_ref = None
            profile.status = "provisioning"
            worker = None

    if worker is None:
        chosen: HermesWorker | None = None
        if prefer_worker_id:
            cand = db.query(HermesWorker).filter(HermesWorker.worker_id == prefer_worker_id).one_or_none()
            if cand and cand.status == "ready":
                others = (
                    db.query(HermesProfile)
                    .filter(
                        HermesProfile.worker_id == cand.worker_id,
                        HermesProfile.id != profile.id,
                        HermesProfile.status.in_(("ready", "provisioning", "assigned")),
                    )
                    .count()
                )
                cap = cand.max_profiles
                if cap is None or others < int(cap):
                    chosen = cand
        if chosen is None:
            chosen = _pick_free_worker(db)
        if chosen is not None:
            profile.worker_id = chosen.worker_id
            profile.credential_ref = chosen.api_server_key_env
            profile.status = "ready"
            profile.last_checked_at = datetime.now(timezone.utc)
            worker = chosen
        elif allow_provision_without_worker:
            profile.status = "provisioning"
            profile.worker_id = None
            profile.credential_ref = None
        else:
            profile.status = "unavailable"
            db.add(profile)
            _mirror_settings_runtime(db, tenant, profile, None)
            db.commit()
            db.refresh(profile)
            raise PlacementError(
                "hermes_runtime_pool_exhausted",
                status=503,
                detail={
                    "tenant": tenant.slug,
                    "profile_id": profile.profile_id,
                    "hint": (
                        "No free Hermes multiplex capacity. "
                        "Raise HERMES_WORKER_MAX_PROFILES or add workers. "
                        "Do not route to another tenant."
                    ),
                },
            )

    api_key = _worker_api_key(worker) if worker else ""
    live_home = ensure_live_profile_home(
        pid,
        worker_id=worker.worker_id if worker else None,
        mcp_url=_internal_mcp_url(),
        api_server_key=api_key or None,
        delno_mcp_key=tenant_mcp_key,
    )
    live_path = str(live_home)

    profile.state_location = live_path
    meta = dict(profile.meta or {})
    meta["api_skeleton_home"] = api_home
    meta["live_profile_home"] = live_path
    meta["worker_bind"] = worker_bind_hint(pid, worker_id=worker.worker_id if worker else None)
    meta["isolation"] = "multiplex_profiles"
    profile.meta = meta
    profile.actor_user_id = profile.actor_user_id or ctx.user_id
    db.add(profile)
    _mirror_settings_runtime(db, tenant, profile, worker)
    db.commit()
    db.refresh(profile)
    return profile


def resolve_placement(db: Session, ctx: TenantContext) -> dict[str, Any]:
    """Return runtime dict for bridge. Fail closed — never default to worker A."""
    profile = get_company_profile(db, ctx.tenant_id)
    if profile is None:
        profile = ensure_tenant_placement(db, ctx)

    if profile.status in ("provisioning", "unavailable") or not profile.worker_id:
        raise PlacementError(
            "hermes_runtime_provisioning"
            if profile.status == "provisioning"
            else "hermes_runtime_unavailable",
            status=503,
            detail={
                "tenant_id": str(ctx.tenant_id),
                "tenant_slug": ctx.tenant_slug,
                "profile_id": profile.profile_id,
                "status": profile.status,
                "hint": "Wait for worker assignment; do not use another company's Hermes.",
            },
        )

    worker = db.query(HermesWorker).filter(HermesWorker.worker_id == profile.worker_id).one_or_none()
    if worker is None or worker.status == "offline":
        raise PlacementError(
            "hermes_worker_offline",
            status=503,
            detail={"worker_id": profile.worker_id, "profile_id": profile.profile_id},
        )

    key_env = worker.api_server_key_env or profile.credential_ref or ""
    api_key = os.environ.get(key_env) or ""
    if not api_key:
        raise PlacementError(
            "hermes_api_key_missing_for_worker",
            status=503,
            detail={"env": key_env, "worker_id": worker.worker_id},
        )

    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    tenant_mcp_key = ensure_mcp_api_key(db, tenant)
    # Ensure multiplex home + profile-scoped keys exist before traffic.
    ensure_live_profile_home(
        profile.profile_id,
        worker_id=worker.worker_id,
        mcp_url=_internal_mcp_url(),
        api_server_key=api_key,
        delno_mcp_key=tenant_mcp_key,
    )

    prefix = f"/p/{profile.profile_id}"
    base = f"{worker.base_url.rstrip('/')}{prefix}"
    return {
        "base_url": base,
        "api_key": api_key,
        "record": {
            "profile_id": profile.profile_id,
            "agent_id": profile.agent_id,
            "worker_id": worker.worker_id,
            "slot_id": worker.worker_id,
            "runtime_base_url": base,
            "api_path_prefix": prefix,
            "api_server_key_env": key_env,
            "state_location": profile.state_location,
            "status": profile.status,
            "pin": profile.pin,
            "isolation": "multiplex_profiles",
        },
        "profile": profile,
        "worker": worker,
    }


def admin_assign_worker(
    db: Session,
    *,
    tenant_id: UUID,
    worker_id: str,
    actor_user_id: UUID | None = None,
) -> HermesProfile:
    """Platform-admin only: pin a tenant profile to a specific multiplex worker."""
    ensure_worker_catalog(db)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).one()
    worker = db.query(HermesWorker).filter(HermesWorker.worker_id == worker_id).one_or_none()
    if worker is None:
        raise PlacementError("hermes_worker_not_found", status=404, detail={"worker_id": worker_id})

    others = (
        db.query(HermesProfile)
        .filter(
            HermesProfile.worker_id == worker_id,
            HermesProfile.tenant_id != tenant_id,
            HermesProfile.status.in_(("ready", "provisioning", "assigned")),
        )
        .all()
    )
    cap = worker.max_profiles
    if cap is not None and len(others) >= int(cap):
        raise PlacementError(
            "hermes_worker_busy",
            status=409,
            detail={
                "worker_id": worker_id,
                "held_by": [str(o.tenant_id) for o in others],
                "max_profiles": cap,
            },
        )

    ctx = TenantContext(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        user_id=actor_user_id,
        role="platform_admin",
    )
    profile = ensure_tenant_placement(db, ctx, prefer_worker_id=worker_id)
    # Force pin even if previously elsewhere (move).
    if profile.worker_id and profile.worker_id != worker_id:
        profile.worker_id = None
    profile.worker_id = worker.worker_id
    profile.credential_ref = worker.api_server_key_env
    profile.status = "ready"
    profile.last_checked_at = datetime.now(timezone.utc)
    api_key = _worker_api_key(worker)
    tenant_mcp_key = ensure_mcp_api_key(db, tenant)
    live = ensure_live_profile_home(
        profile.profile_id,
        worker_id=worker.worker_id,
        mcp_url=_internal_mcp_url(),
        api_server_key=api_key or None,
        delno_mcp_key=tenant_mcp_key,
    )
    profile.state_location = str(live)
    db.add(profile)
    _mirror_settings_runtime(db, tenant, profile, worker)
    db.commit()
    db.refresh(profile)
    return profile


def list_placement_snapshot(db: Session) -> dict[str, Any]:
    ensure_worker_catalog(db)
    workers = db.query(HermesWorker).order_by(HermesWorker.worker_id.asc()).all()
    profiles = db.query(HermesProfile).order_by(HermesProfile.created_at.asc()).all()
    return {
        "ok": True,
        "pin": PIN,
        "mode": "multiplex_pool",
        "default_max_profiles": default_max_profiles(),
        "workers": [
            {
                "worker_id": w.worker_id,
                "base_url": w.base_url,
                "status": w.status,
                "max_profiles": w.max_profiles,
                "open_profiles": _worker_open_profile_count(db, w.worker_id),
                "api_server_key_env": w.api_server_key_env,
                "image_digest": w.image_digest,
            }
            for w in workers
        ],
        "profiles": [
            {
                "tenant_id": str(p.tenant_id),
                "profile_id": p.profile_id,
                "agent_id": p.agent_id,
                "worker_id": p.worker_id,
                "status": p.status,
                "state_location": p.state_location,
                "pin": p.pin,
            }
            for p in profiles
        ],
        "rules": {
            "no_fallback_to_default_worker": True,
            "no_shared_delno_mcp_key_across_tenants": True,
            "multiplex_profiles": True,
            "api_path": "/p/<profile_id>/v1/...",
            "mcp_internal_only": True,
            "capacity_env": "HERMES_WORKER_MAX_PROFILES",
        },
    }
