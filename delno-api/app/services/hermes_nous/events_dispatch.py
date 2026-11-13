"""Wire platform events → durable Hermes tasks (P3). Best-effort, never breaks lead create."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.feature_flag import FeatureFlag
from app.models.tenant import Tenant
from app.services.hermes_nous.flags import FLAG_HERMES_NOUS_RUNTIME
from app.services.hermes_nous.tasks import create_task, record_run, add_step


def _flag_on(db: Session, tenant_id: UUID) -> bool:
    row = (
        db.query(FeatureFlag)
        .filter(
            FeatureFlag.tenant_id == tenant_id,
            FeatureFlag.flag_key == FLAG_HERMES_NOUS_RUNTIME,
        )
        .one_or_none()
    )
    return bool(row and row.enabled)


def on_lead_created(
    db: Session,
    *,
    tenant_id: UUID,
    lead_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """If hermes_nous_runtime enabled — create durable task + queued run for the lead."""
    try:
        if not _flag_on(db, tenant_id):
            return None
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).one_or_none()
        if not tenant:
            return None
        ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="system")
        goal = (
            f"Новая заявка {lead_id}: разбери лид, проверь дубликаты в CRM/KB, "
            f"подготовь следующий шаг владельцу. source={(payload or {}).get('source')}"
        )
        task = create_task(
            db,
            ctx,
            goal=goal,
            trigger_kind="event",
            trigger_config={"event": "lead.created", "lead_id": lead_id, **(payload or {})},
        )
        run = record_run(
            db,
            ctx,
            hermes_run_id=None,
            task_id=task.id,
            status="queued",
            summary=f"lead.created:{lead_id}",
        )
        add_step(
            db,
            ctx,
            run.id,
            kind="note",
            safe_summary="Заявка поставлена в очередь Гермеса",
            status="completed",
        )
        return {"ok": True, "task_id": str(task.id), "run_id": str(run.id)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
