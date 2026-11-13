"""Owner-facing Nous Hermes API: status, office loop, runs, durable tasks (P0–P3).

Security (2026-11-13):
- Clients cannot set runtime_base_url, foreign profile/session, or escalate tool_ids.
- Provisioning of worker assignment is platform-admin (or internal placement).
- Owner may only ensure/refresh THEIR profile placement.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_tenant_context_auth, require_platform_admin
from app.core.db import get_db
from app.core.tenant import TenantContext
from app.models.user import User
from app.services.hermes_nous.bridge import HermesBridgeError, create_run, get_run, stop_run
from app.services.hermes_nous.flags import FLAG_HERMES_NOUS_RUNTIME, is_hermes_nous_enabled
from app.services.hermes_nous.onboarding import (
    confirm_kb_draft,
    get_office_loop,
    save_kb_draft,
    set_phase,
)
from app.services.hermes_nous.placement import (
    PlacementError,
    admin_assign_worker,
    ensure_tenant_placement,
    get_company_profile,
    list_placement_snapshot,
)
from app.services.hermes_nous.provision import tenant_runtime_record
from app.services.hermes_nous.run_tokens import issue_run_token, revoke_run_token
from app.services.hermes_nous.tasks import (
    create_task,
    list_runs,
    list_steps,
    list_tasks,
    pause_task,
    resume_task,
    run_to_dict,
    step_to_dict,
    task_to_dict,
)
from app.services.hermes_nous.tool_packs import pack_for_mode
from app.services.hermes_nous.toolkit import get_toolkit

router = APIRouter(prefix="/hermes-nous", tags=["hermes-nous"])


def _require_flag(db: Session, ctx: TenantContext) -> None:
    if not is_hermes_nous_enabled(db, ctx):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "hermes_nous_runtime_disabled",
                "flag": FLAG_HERMES_NOUS_RUNTIME,
                "hint": "Enable feature flag hermes_nous_runtime for this tenant.",
            },
        )


def _clamp_tools(requested: list[str] | None, mode: str) -> list[str]:
    """Intersect client tool_ids with the pack for mode — never allow escalation."""
    allowed = set(pack_for_mode(mode))
    if not requested:
        return sorted(allowed)
    out = [t for t in requested if str(t).strip() in allowed]
    return out or sorted(allowed)


class ProvisionBody(BaseModel):
    """Owner provision: no client-chosen runtime. Kept for API compat."""

    pass


class RunCreateBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    conversation_id: str | None = Field(default=None, max_length=200)
    mode: str = Field(default="onboarding", max_length=32)
    idempotency_key: str | None = Field(default=None, max_length=255)
    task_id: UUID | None = None
    # Deprecated: ignored for escalation; intersected with pack if present.
    tool_ids: list[str] = Field(default_factory=list, max_length=128)
    # Deprecated: client cannot set foreign session — server builds from tenant+conversation.
    session_id: str | None = Field(default=None, max_length=200)


class PhaseBody(BaseModel):
    phase: str = Field(..., max_length=32)


class KbDraftBody(BaseModel):
    title: str = Field(default="Профиль компании", max_length=200)
    body: str = Field(..., min_length=1, max_length=50_000)
    source_url: str | None = Field(default=None, max_length=500)


class TaskCreateBody(BaseModel):
    goal: str = Field(..., min_length=1, max_length=8000)
    trigger_kind: str = Field(default="manual", max_length=32)
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    hermes_cron_id: str | None = Field(default=None, max_length=120)


class MintTokenBody(BaseModel):
    mode: str = Field(default="onboarding", max_length=32)
    # Deprecated escalation vector — clamped to pack.
    tool_ids: list[str] = Field(default_factory=list, max_length=128)


class AdminAssignBody(BaseModel):
    tenant_id: UUID
    worker_id: str = Field(..., min_length=1, max_length=64)


@router.get("/status")
def nous_status(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    enabled = is_hermes_nous_enabled(db, ctx)
    runtime = tenant_runtime_record(db, ctx)
    profile = get_company_profile(db, ctx.tenant_id)
    loop = get_office_loop(db, ctx) if enabled else None
    return {
        "ok": True,
        "flag": FLAG_HERMES_NOUS_RUNTIME,
        "enabled": enabled,
        "engine": "nous_hermes_agent",
        "pin": "v0.23.1",
        "runtime": runtime,
        "profile": {
            "profile_id": profile.profile_id if profile else None,
            "worker_id": profile.worker_id if profile else None,
            "status": profile.status if profile else "missing",
            "state_location": profile.state_location if profile else None,
            "agent_id": profile.agent_id if profile else "company_main",
        },
        "office_loop": loop,
        "diy_loop": "admin_emergency_only_when_flag_off",
        "master_plan_phases": ["P0", "P1", "P2", "P3", "P4", "P5"],
        "telephony": "codex_zone_do_not_overwrite",
        "mcp": {
            "public_api_note": "api.dlno.ru is SNI-routed; Hermes must use internal DELNO MCP URL",
            "prefer_run_token": True,
            "legacy_mcp_key": "not_for_model_office_tools",
        },
    }


@router.get("/office-loop")
def office_loop(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    """P1 product surface — works even before Nous runtime is up (uses DELNO setup)."""
    return get_office_loop(db, ctx)


@router.post("/office-loop/phase")
def office_loop_phase(
    body: PhaseBody,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    out = set_phase(db, ctx, body.phase)
    if not out.get("ok", True) and out.get("error"):
        raise HTTPException(status_code=400, detail=out)
    return out


@router.post("/kb-draft")
def kb_draft_save(
    body: KbDraftBody,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    return save_kb_draft(
        db, ctx, title=body.title, body=body.body, source_url=body.source_url
    )


@router.post("/kb-draft/confirm")
def kb_draft_confirm(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    out = confirm_kb_draft(db, ctx)
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out)
    return out


@router.post("/provision")
def nous_provision(
    _body: ProvisionBody | None = None,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    """Ensure THIS tenant's profile placement. No client runtime_base_url."""
    _require_flag(db, ctx)
    try:
        profile = ensure_tenant_placement(db, ctx)
    except PlacementError as exc:
        raise HTTPException(status_code=exc.status, detail={"error": exc.code, **exc.detail}) from exc
    return {
        "ok": True,
        "runtime": tenant_runtime_record(db, ctx),
        "profile": {
            "profile_id": profile.profile_id,
            "worker_id": profile.worker_id,
            "status": profile.status,
            "state_location": profile.state_location,
        },
    }


@router.post("/runs")
def nous_create_run(
    body: RunCreateBody,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    _require_flag(db, ctx)
    tools = _clamp_tools(body.tool_ids, body.mode)
    # Server builds session — ignore client session_id unless it already matches tenant prefix.
    conv = body.conversation_id or body.session_id
    session_id = f"{ctx.tenant_slug}:{conv}" if conv else None
    try:
        return create_run(
            db,
            ctx,
            message=body.message,
            session_id=session_id,
            tool_ids=tools,
            idempotency_key=body.idempotency_key,
            task_id=body.task_id,
            mode=body.mode,
        )
    except HermesBridgeError as exc:
        raise HTTPException(
            status_code=exc.status or 503,
            detail={"error": str(exc), "body": exc.body},
        ) from exc


@router.get("/runs")
def nous_list_runs(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
    limit: int = Query(default=30, ge=1, le=100),
) -> dict[str, Any]:
    runs = list_runs(db, ctx, limit=limit)
    return {"ok": True, "items": [run_to_dict(r) for r in runs]}


@router.get("/runs/{run_id}")
def nous_get_run(
    run_id: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    _require_flag(db, ctx)
    try:
        return get_run(db, ctx, run_id)
    except HermesBridgeError as exc:
        raise HTTPException(
            status_code=exc.status or 503,
            detail={"error": str(exc), "body": exc.body},
        ) from exc


@router.get("/runs/{run_id}/steps")
def nous_run_steps(
    run_id: UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    steps = list_steps(db, ctx, run_id)
    return {"ok": True, "items": [step_to_dict(s) for s in steps]}


@router.post("/runs/{run_id}/stop")
def nous_stop_run(
    run_id: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    _require_flag(db, ctx)
    try:
        out = stop_run(db, ctx, run_id)
        revoke_run_token(db, ctx, run_id=run_id)
        return out
    except HermesBridgeError as exc:
        raise HTTPException(
            status_code=exc.status or 503,
            detail={"error": str(exc), "body": exc.body},
        ) from exc


@router.get("/tasks")
def nous_list_tasks(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    items = list_tasks(db, ctx, limit=limit)
    return {"ok": True, "items": [task_to_dict(t) for t in items]}


@router.post("/tasks")
def nous_create_task(
    body: TaskCreateBody,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    task = create_task(
        db,
        ctx,
        goal=body.goal,
        trigger_kind=body.trigger_kind,
        trigger_config=body.trigger_config,
        hermes_cron_id=body.hermes_cron_id,
    )
    return {"ok": True, "task": task_to_dict(task)}


@router.post("/tasks/{task_id}/pause")
def nous_pause_task(
    task_id: UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    task = pause_task(db, ctx, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    return {"ok": True, "task": task_to_dict(task)}


@router.post("/tasks/{task_id}/resume")
def nous_resume_task(
    task_id: UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    task = resume_task(db, ctx, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    return {"ok": True, "task": task_to_dict(task)}


@router.get("/toolkit")
def nous_toolkit(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    """Connectors + Ava telephony tools + media tools inventory for the cabinet panel."""
    return get_toolkit(db, ctx)


@router.get("/channels-map")
def channels_map(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    """P4 stub: how owner Hermes vs frontline channels are supposed to bind."""
    return {
        "ok": True,
        "tenant_id": str(ctx.tenant_id),
        "owner_surface": "cabinet + /v1/hermes-nous",
        "frontline_surfaces": ["telegram", "max", "widget", "phone"],
        "rule": "Channels are pipes; Owner Hermes orchestrates; Frontline reads KB of this tenant only.",
        "telephony": "Codex trunk_id routing — do not overwrite from this API",
        "status": "documented_stub",
    }


@router.get("/scale-notes")
def scale_notes(
    _db: Session = Depends(get_db),
    _ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    """P5 stub metrics policy."""
    return {
        "ok": True,
        "phase": "P5",
        "policy": {
            "runtime_per_tenant_until_mcp_isolation_proven": True,
            "measure_idle_rss_before_100_tenants": True,
            "bill_per_run_tokens": True,
            "multiplex_blocked_until_issue_67605": True,
            "placement": "hermes_profiles + hermes_workers",
            "no_container_per_tenant": True,
        },
    }


@router.post("/run-tokens")
def nous_mint_token(
    body: MintTokenBody,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    """Diagnostic mint — tools clamped to pack. Prefer create_run bindings in production."""
    _require_flag(db, ctx)
    tools = _clamp_tools(body.tool_ids, body.mode)
    issued = issue_run_token(db, ctx, tool_ids=tools)
    return {
        "ok": True,
        "token": issued.token,
        "run_id": issued.run_id,
        "expires_at": issued.expires_at,
        "tool_ids": issued.tool_ids,
        "mode": body.mode,
        "note": "tool_ids clamped to pack; prefer POST /runs which binds server-side",
    }


@router.post("/tasks/tick")
def nous_tasks_tick(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
    limit: int = Query(default=5, ge=1, le=20),
) -> dict[str, Any]:
    """Manually claim+run due scheduled tasks for this tenant (also runs on API ticker)."""
    from app.services.agent_schedule import claim_due_tasks, execute_scheduled_task

    _require_flag(db, ctx)
    due = claim_due_tasks(db, limit=limit, tenant_id=ctx.tenant_id)
    results = [execute_scheduled_task(db, t) for t in due]
    return {"ok": True, "claimed": len(due), "results": results}


@router.get("/placement")
def nous_placement_diag(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    """Safe diagnostic: this tenant's profile only (not the full pool map)."""
    profile = get_company_profile(db, ctx.tenant_id)
    return {
        "ok": True,
        "tenant_id": str(ctx.tenant_id),
        "tenant_slug": ctx.tenant_slug,
        "profile": None
        if profile is None
        else {
            "profile_id": profile.profile_id,
            "worker_id": profile.worker_id,
            "status": profile.status,
            "agent_id": profile.agent_id,
            "pin": profile.pin,
            "state_location": profile.state_location,
        },
    }


@router.get("/admin/placement")
def admin_placement_snapshot(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> dict[str, Any]:
    return list_placement_snapshot(db)


@router.post("/admin/assign-worker")
def admin_assign(
    body: AdminAssignBody,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
) -> dict[str, Any]:
    try:
        profile = admin_assign_worker(
            db,
            tenant_id=body.tenant_id,
            worker_id=body.worker_id,
            actor_user_id=admin.id,
        )
    except PlacementError as exc:
        raise HTTPException(status_code=exc.status, detail={"error": exc.code, **exc.detail}) from exc
    return {
        "ok": True,
        "profile_id": profile.profile_id,
        "worker_id": profile.worker_id,
        "status": profile.status,
        "tenant_id": str(profile.tenant_id),
    }
