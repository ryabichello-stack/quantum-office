"""Durable agent_tasks / runs control-plane helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.agent_task import AgentRun, AgentStep, AgentTask


def create_task(
    db: Session,
    ctx: TenantContext,
    *,
    goal: str,
    trigger_kind: str = "manual",
    trigger_config: dict[str, Any] | None = None,
    hermes_cron_id: str | None = None,
) -> AgentTask:
    task = AgentTask(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        owner_user_id=ctx.user_id,
        goal=goal.strip()[:8000],
        trigger_kind=trigger_kind if trigger_kind in ("manual", "event", "schedule") else "manual",
        trigger_config=trigger_config or {},
        status="active",
        hermes_cron_id=hermes_cron_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def list_tasks(db: Session, ctx: TenantContext, *, limit: int = 50) -> list[AgentTask]:
    return (
        db.query(AgentTask)
        .filter(AgentTask.tenant_id == ctx.tenant_id)
        .order_by(AgentTask.created_at.desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )


def pause_task(db: Session, ctx: TenantContext, task_id: uuid.UUID) -> AgentTask | None:
    task = (
        db.query(AgentTask)
        .filter(AgentTask.tenant_id == ctx.tenant_id, AgentTask.id == task_id)
        .one_or_none()
    )
    if not task:
        return None
    task.status = "paused"
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def resume_task(db: Session, ctx: TenantContext, task_id: uuid.UUID) -> AgentTask | None:
    task = (
        db.query(AgentTask)
        .filter(AgentTask.tenant_id == ctx.tenant_id, AgentTask.id == task_id)
        .one_or_none()
    )
    if not task:
        return None
    task.status = "active"
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def record_run(
    db: Session,
    ctx: TenantContext,
    *,
    hermes_run_id: str | None,
    task_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
    status: str = "running",
    summary: str | None = None,
    usage: dict[str, Any] | None = None,
) -> AgentRun:
    run = AgentRun(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        task_id=task_id,
        hermes_run_id=hermes_run_id,
        conversation_id=conversation_id,
        status=status,
        result_summary=summary,
        usage=usage or {},
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def add_step(
    db: Session,
    ctx: TenantContext,
    run_id: uuid.UUID,
    *,
    kind: str,
    safe_summary: str,
    tool_id: str | None = None,
    status: str = "running",
) -> AgentStep:
    step = AgentStep(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        run_id=run_id,
        kind=kind,
        tool_id=tool_id,
        status=status,
        safe_summary=safe_summary[:2000],
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    return step


def list_runs(db: Session, ctx: TenantContext, *, limit: int = 30) -> list[AgentRun]:
    return (
        db.query(AgentRun)
        .filter(AgentRun.tenant_id == ctx.tenant_id)
        .order_by(AgentRun.created_at.desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )


def list_steps(db: Session, ctx: TenantContext, run_id: uuid.UUID) -> list[AgentStep]:
    return (
        db.query(AgentStep)
        .filter(AgentStep.tenant_id == ctx.tenant_id, AgentStep.run_id == run_id)
        .order_by(AgentStep.created_at.asc())
        .all()
    )


def task_to_dict(t: AgentTask) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "goal": t.goal,
        "trigger_kind": t.trigger_kind,
        "trigger_config": t.trigger_config or {},
        "status": t.status,
        "hermes_cron_id": t.hermes_cron_id,
        "next_run_at": t.next_run_at.isoformat() if t.next_run_at else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def run_to_dict(r: AgentRun) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "task_id": str(r.task_id) if r.task_id else None,
        "hermes_run_id": r.hermes_run_id,
        "status": r.status,
        "result_summary": r.result_summary,
        "usage": r.usage or {},
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def step_to_dict(s: AgentStep) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "run_id": str(s.run_id),
        "kind": s.kind,
        "tool_id": s.tool_id,
        "status": s.status,
        "safe_summary": s.safe_summary,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }
