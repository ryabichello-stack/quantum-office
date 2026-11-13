"""Hermes supervisor tools — setup checklist + health watch + alerts."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.operator.tools.registry import ToolResult
from app.services import hermes_ops


class HermesSetupStatusTool:
    name = "hermes.setup_status"
    description = (
        "First-time office setup checklist for this tenant: KB, phone, Telegram/MAX, "
        "calendar, mail, conference. Hermes uses this to guide the owner."
    )
    critical_write = False
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        out = hermes_ops.office_setup_status(db, ctx)
        return ToolResult(ok=True, data=out, message=out.get("message_ru") or "ok")


class HermesSetupMarkTool:
    name = "hermes.setup_mark"
    description = (
        "Mark Hermes setup progress after a REAL completed fact "
        "(e.g. telephony script saved). "
        "Do NOT use after office.build_kb_draft — show the profile and use "
        "office.confirm_kb_draft when the owner agrees. "
        "Do NOT use to skip phone/SIP/Telegram steps."
    )
    critical_write = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "kb_ready": {"type": "boolean"},
            "note": {"type": "string"},
        },
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        kb = params.get("kb_ready")
        out = hermes_ops.mark_setup_progress(
            db,
            ctx,
            kb_ready=bool(kb) if kb is not None else None,
            note=str(params.get("note") or "") or None,
        )
        return ToolResult(ok=True, data=out, message=out.get("message_ru") or "ok")


class HermesHealthTool:
    name = "hermes.health"
    description = (
        "Check that connected office components work (phones, channels, connectors, call queue). "
        "Returns alerts Hermes must tell the owner about."
    )
    critical_write = False
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        out = hermes_ops.office_health_report(db, ctx)
        return ToolResult(
            ok=True,
            data=out,
            message=out.get("message_ru") or ("healthy" if out.get("healthy") else "degraded"),
        )


class HermesAlertsTool:
    name = "hermes.alerts"
    description = "List recent office.alert / health events for the tenant."
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {"limit": {"type": "integer", "default": 20}},
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        out = hermes_ops.list_recent_office_alerts(db, ctx, limit=int(params.get("limit") or 20))
        return ToolResult(ok=True, data=out, message=f"{len(out.get('items') or [])} events")


class HermesCapabilitiesTool:
    name = "hermes.capabilities"
    description = (
        "Discover the current tenant's office tools and connector readiness. "
        "Use before onboarding or planning work across channels; distinguish a reachable service "
        "from a usable account and explain missing access."
    )
    critical_write = False
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        from app.operator.agent import CABINET_LLM_TOOLS
        from app.operator.tools.registry import registry
        from app.services.connectors import list_tenant_connector_readiness

        connectors = list_tenant_connector_readiness(db, ctx)
        allowed = set(CABINET_LLM_TOOLS)
        tools = [
            {"name": t["name"], "confirmation_class": t["confirmation_class"]}
            for t in registry.list_catalog() if t["name"] in allowed
        ]
        missing = [c["kind"] for c in connectors if not c["usable"]]
        for row in connectors:
            if not isinstance(row, dict):
                continue
            usable = bool(row.get("usable"))
            enabled = bool(row.get("enabled"))
            # Align with hermes_ops: never let platform upstream look "configured".
            row["ready"] = usable
            row["configured"] = usable
            row["ok"] = usable
            row["summary_ru"] = (
                "подключено для этого кабинета"
                if usable
                else (
                    f"включено, но не usable ({row.get('reason') or 'нет кредов'})"
                    if enabled
                    else "у этого кабинета НЕ подключено"
                )
            )
        return ToolResult(
            ok=True,
            data={"connectors": connectors, "tools": tools, "missing": missing},
            message=(
                "Готовность ЭТОГО кабинета (не платформы). Требуют настройки: "
                + (", ".join(missing) if missing else "нет")
            ),
        )


class HermesTasksCreateTool:
    name = "hermes.tasks_create"
    description = (
        "Create a periodic Hermes office task (schedule). "
        "Use when the owner asks to check something every N minutes/hours/days "
        "(заявки, почта, сайт, здоровье офиса). "
        "every_minutes: 1..10080. Goal = what to do on each tick."
    )
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "goal": {"type": "string"},
            "every_minutes": {"type": "integer", "default": 60},
            "run_immediately": {"type": "boolean", "default": False},
        },
        "required": ["goal"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        from app.services.agent_schedule import create_scheduled_task
        from app.services.hermes_nous.tasks import task_to_dict

        goal = str(params.get("goal") or "").strip()
        if not goal:
            return ToolResult(ok=False, data={}, message="goal_required")
        every = int(params.get("every_minutes") or 60)
        every = max(1, min(every, 7 * 24 * 60))
        task = create_scheduled_task(
            db,
            ctx,
            goal=goal,
            every_minutes=every,
            run_immediately=bool(params.get("run_immediately")),
        )
        data = task_to_dict(task)
        return ToolResult(
            ok=True,
            data=data,
            message=(
                f"Поручение создано: каждые {every} мин — «{goal[:120]}». "
                f"Следующий запуск: {data.get('next_run_at') or 'скоро'}. id={task.id}"
            ),
        )


class HermesTasksListTool:
    name = "hermes.tasks_list"
    description = "List Hermes office tasks / scheduled поручения for this tenant."
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {"limit": {"type": "integer", "default": 30}},
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        from app.services.agent_schedule import format_tasks_message
        from app.services.hermes_nous.tasks import list_tasks, task_to_dict

        items = list_tasks(db, ctx, limit=int(params.get("limit") or 30))
        return ToolResult(
            ok=True,
            data={"items": [task_to_dict(t) for t in items]},
            message=format_tasks_message(items),
        )


class HermesTasksPauseTool:
    name = "hermes.tasks_pause"
    description = "Pause a scheduled Hermes task by id."
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {"task_id": {"type": "string"}},
        "required": ["task_id"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        import uuid

        from app.services.hermes_nous.tasks import pause_task, task_to_dict

        try:
            tid = uuid.UUID(str(params.get("task_id") or ""))
        except Exception:  # noqa: BLE001
            return ToolResult(ok=False, data={}, message="invalid_task_id")
        task = pause_task(db, ctx, tid)
        if not task:
            return ToolResult(ok=False, data={}, message="task_not_found")
        return ToolResult(ok=True, data=task_to_dict(task), message=f"Поручение на паузе: {task.id}")


class HermesTasksResumeTool:
    name = "hermes.tasks_resume"
    description = "Resume a paused Hermes scheduled task by id."
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {"task_id": {"type": "string"}},
        "required": ["task_id"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        import uuid
        from datetime import datetime, timezone

        from app.services.agent_schedule import compute_next_run
        from app.services.hermes_nous.tasks import resume_task, task_to_dict

        try:
            tid = uuid.UUID(str(params.get("task_id") or ""))
        except Exception:  # noqa: BLE001
            return ToolResult(ok=False, data={}, message="invalid_task_id")
        task = resume_task(db, ctx, tid)
        if not task:
            return ToolResult(ok=False, data={}, message="task_not_found")
        every = int((task.trigger_config or {}).get("every_minutes") or 60)
        if task.trigger_kind == "schedule":
            task.next_run_at = compute_next_run(every, from_dt=datetime.now(timezone.utc))
            db.add(task)
            db.commit()
            db.refresh(task)
        return ToolResult(ok=True, data=task_to_dict(task), message=f"Поручение возобновлено: {task.id}")
