"""Periodic Hermes office tasks — create, claim due, execute."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.agent_task import AgentTask
from app.models.tenant import Tenant
from app.services.hermes_nous.tasks import add_step, create_task, list_tasks, record_run, task_to_dict

logger = logging.getLogger(__name__)

_EVERY_RE = re.compile(
    r"(?:каждые|каждый|каждую|каждое|every)\s+(\d+)?\s*"
    r"(минут\w*|мин|minute\w*|час\w*|hour\w*|дн\w*|день|сутк\w*|day\w*|недел\w*|week\w*)",
    re.I,
)
_ONCE_HOUR = re.compile(r"\b(ежечасно|каждый\s+час|once\s+an?\s+hour|hourly)\b", re.I)
_ONCE_DAY = re.compile(r"\b(ежедневно|каждый\s+день|раз\s+в\s+день|daily)\b", re.I)


def wants_tasks_list(message: str) -> bool:
    low = (message or "").lower()
    return any(
        m in low
        for m in (
            "какие поручен",
            "список поручен",
            "мои поручен",
            "активные задач",
            "задачи по расписанию",
            "hermes.tasks_list",
            "list tasks",
            "scheduled tasks",
        )
    )

def wants_tasks_pause(message: str) -> bool:
    low = (message or "").lower()
    return any(m in low for m in ("останови поручен", "пауза поручен", "pause task", "останови задач"))

def parse_schedule_intent(message: str) -> dict[str, Any] | None:
    """
    Detect «проверяй X каждый час» style goals.
    Returns {goal, every_minutes} or None.
    """
    text = (message or "").strip()
    if not text:
        return None
    low = text.lower()
    # Listing / pausing is not "create schedule".
    if wants_tasks_list(text) or wants_tasks_pause(text):
        return None
    create_markers = (
        "проверяй",
        "проверять",
        "монитор",
        "следи",
        "следить",
        "периодически",
        "каждый час",
        "каждые ",
        "ежедневно",
        "ежечасно",
        "cron",
        "schedule",
        "поставь задачу",
        "создай задачу",
        "создай поручение",
        "поставь поручение",
        "заведи поручение",
        "по расписанию проверя",
        "по расписанию следи",
    )
    if not any(v in low for v in create_markers):
        return None

    every_minutes: int | None = None
    if _ONCE_HOUR.search(text):
        every_minutes = 60
    elif _ONCE_DAY.search(text):
        every_minutes = 24 * 60
    else:
        m = _EVERY_RE.search(text)
        if m:
            n = int(m.group(1) or "1")
            unit = (m.group(2) or "").lower()
            if unit.startswith(("мин", "min")):
                every_minutes = max(1, n)
            elif unit.startswith(("час", "hour")):
                every_minutes = max(1, n * 60)
            elif unit.startswith(("дн", "день", "сут", "day")):
                every_minutes = max(1, n * 24 * 60)
            elif unit.startswith(("недел", "week")):
                every_minutes = max(1, n * 7 * 24 * 60)

    if every_minutes is None:
        # Default for bare «поставь поручение проверять заявки»
        if any(v in low for v in ("поручен", "по расписанию", "периодически", "schedule", "cron")):
            every_minutes = 60
        else:
            return None

    # Cap: 1 min … 7 days
    every_minutes = max(1, min(every_minutes, 7 * 24 * 60))
    goal = text
    # Strip schedule noise from goal when obvious
    goal = _EVERY_RE.sub("", goal)
    goal = _ONCE_HOUR.sub("", goal)
    goal = _ONCE_DAY.sub("", goal)
    for junk in (
        "по расписанию",
        "периодически",
        "поставь задачу",
        "создай задачу",
        "создай поручение",
        "поручение:",
    ):
        goal = re.sub(re.escape(junk), "", goal, flags=re.I)
    goal = re.sub(r"\s{2,}", " ", goal).strip(" —-:") or text
    return {"goal": goal[:8000], "every_minutes": every_minutes}


def compute_next_run(every_minutes: int, *, from_dt: datetime | None = None) -> datetime:
    base = from_dt or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base + timedelta(minutes=max(1, int(every_minutes)))


def create_scheduled_task(
    db: Session,
    ctx: TenantContext,
    *,
    goal: str,
    every_minutes: int,
    run_immediately: bool = False,
) -> AgentTask:
    cfg = {"every_minutes": int(every_minutes), "timezone": "UTC"}
    next_at = datetime.now(timezone.utc) if run_immediately else compute_next_run(every_minutes)
    task = create_task(
        db,
        ctx,
        goal=goal,
        trigger_kind="schedule",
        trigger_config=cfg,
    )
    task.next_run_at = next_at
    db.add(task)
    db.commit()
    db.refresh(task)
    return task




def claim_due_tasks(
    db: Session,
    *,
    limit: int = 10,
    tenant_id: uuid.UUID | None = None,
) -> list[AgentTask]:
    now = datetime.now(timezone.utc)
    q = db.query(AgentTask).filter(
        AgentTask.status == "active",
        AgentTask.trigger_kind == "schedule",
        AgentTask.next_run_at.isnot(None),
        AgentTask.next_run_at <= now,
    )
    if tenant_id is not None:
        q = q.filter(AgentTask.tenant_id == tenant_id)
    rows = (
        q.order_by(AgentTask.next_run_at.asc())
        .limit(max(1, min(limit, 50)))
        .all()
    )
    claimed: list[AgentTask] = []
    for task in rows:
        every = int((task.trigger_config or {}).get("every_minutes") or 60)
        # Push next_run forward immediately to avoid double-claim.
        task.next_run_at = compute_next_run(every, from_dt=now)
        db.add(task)
        claimed.append(task)
    if claimed:
        db.commit()
        for t in claimed:
            db.refresh(t)
    return claimed


def execute_scheduled_task(db: Session, task: AgentTask) -> dict[str, Any]:
    """Run one due task.

    When ``hermes_nous_runtime`` is on for the tenant, prefer upstream Hermes
    ``create_run`` (same brain as cabinet). DIY ``run_operator_turn`` is only
    the emergency path when the flag is off or Nous runtime is unavailable.
    """
    from app.operator.agent import run_operator_turn
    from app.services.hermes_nous.flags import is_hermes_nous_enabled

    tenant = db.query(Tenant).filter(Tenant.id == task.tenant_id).one_or_none()
    if not tenant:
        return {"ok": False, "error": "tenant_missing", "task_id": str(task.id)}

    ctx = TenantContext(
        tenant_id=task.tenant_id,
        tenant_slug=tenant.slug,
        role="tenant_owner",
        user_id=task.owner_user_id,
    )
    prompt = (
        "Это периодическое поручение владельца офиса. Выполни цель через tools, "
        "кратко отчитайся по фактам. Не спрашивай подтверждений на чтение; "
        "критичные записи всё равно потребуют confirm policy.\n\n"
        f"Цель: {task.goal}"
    )

    # Prefer Nous Hermes when enabled — do not silently keep DIY as the schedule brain.
    if is_hermes_nous_enabled(db, ctx):
        try:
            from app.services.hermes_nous.bridge import HermesBridgeError, create_run

            nous = create_run(
                db,
                ctx,
                message=prompt,
                session_id=f"{tenant.slug}:schedule:{task.id}",
                task_id=task.id,
                mode="tasks",
            )
            summary = str(nous.get("output") or "")[:4000]
            return {
                "ok": True,
                "engine": "nous_hermes_agent",
                "task_id": str(task.id),
                "run_id": nous.get("delno_agent_run_id") or nous.get("run_id"),
                "hermes_run_id": nous.get("run_id"),
                "reply": summary,
                "tool_calls": [],
            }
        except HermesBridgeError as exc:
            logger.warning(
                "schedule Nous unavailable for task %s (%s) — refusing silent DIY while flag on",
                task.id,
                exc,
            )
            run = record_run(
                db,
                ctx,
                hermes_run_id=f"sched_{uuid.uuid4().hex[:12]}",
                task_id=task.id,
                status="failed",
                summary=task.goal[:500],
            )
            run.error_code = str(exc)[:64]
            run.result_summary = f"hermes_unavailable: {exc}"[:500]
            run.finished_at = datetime.now(timezone.utc)
            db.add(run)
            db.commit()
            return {
                "ok": False,
                "engine": "hermes_unavailable",
                "task_id": str(task.id),
                "run_id": str(run.id),
                "error": str(exc)[:300],
            }

    run = record_run(
        db,
        ctx,
        hermes_run_id=f"sched_{uuid.uuid4().hex[:12]}",
        task_id=task.id,
        status="running",
        summary=task.goal[:500],
    )
    add_step(
        db,
        ctx,
        run.id,
        kind="plan",
        safe_summary=f"Расписание: {task.goal[:200]}",
        status="completed",
    )
    try:
        out = run_operator_turn(
            db,
            ctx,
            message=prompt,
            channel="hermes_schedule",
            conversation_id=None,
            input_modality="text",
            record_user_message=True,
            commit=True,
        )
        summary = str(out.get("reply") or "")[:4000]
        run.status = "completed"
        run.result_summary = summary
        run.finished_at = datetime.now(timezone.utc)
        db.add(run)
        db.commit()
        add_step(
            db,
            ctx,
            run.id,
            kind="note",
            safe_summary=summary[:500] or "done",
            status="completed",
        )
        return {
            "ok": True,
            "engine": "diy_operator",
            "task_id": str(task.id),
            "run_id": str(run.id),
            "reply": summary,
            "tool_calls": out.get("tool_calls") or [],
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("scheduled task failed %s", task.id)
        run.status = "failed"
        run.error_code = "schedule_exec_failed"
        run.result_summary = str(exc)[:500]
        run.finished_at = datetime.now(timezone.utc)
        db.add(run)
        db.commit()
        return {"ok": False, "task_id": str(task.id), "run_id": str(run.id), "error": str(exc)[:300]}


def tick_due_tasks(db: Session, *, limit: int = 5) -> dict[str, Any]:
    due = claim_due_tasks(db, limit=limit)
    results = [execute_scheduled_task(db, t) for t in due]
    return {"ok": True, "claimed": len(due), "results": results}


def format_tasks_message(tasks: list[AgentTask]) -> str:
    if not tasks:
        return "Активных поручений нет. Скажите, например: «проверяй заявки каждый час»."
    lines = ["Поручения:"]
    for t in tasks[:30]:
        cfg = t.trigger_config or {}
        every = cfg.get("every_minutes")
        sched = f"каждые {every} мин" if every else t.trigger_kind
        nxt = t.next_run_at.isoformat() if t.next_run_at else "—"
        lines.append(f"• [{t.status}] {sched} — {t.goal[:160]} (next {nxt}, id={t.id})")
    return "\n".join(lines)
